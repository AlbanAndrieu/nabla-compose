# ClickHouse / Langfuse failure modes

This note records the concrete failures observed while recovering the shared
ClickHouse service and Langfuse 4.30.0 on TrueNAS. It is intentionally
incident-oriented: each entry states the symptom, root cause, recovery, and the
repository guard that should prevent recurrence.

## 1. TrueNAS Custom App turned prometheus.xml into a directory

### Symptom

ClickHouse could not consume the expected configuration file:

```text
/etc/clickhouse-server/config.d/prometheus.xml
```

The bind target existed, but it was not a regular file.

### Root cause

The full application Compose was copied into the TrueNAS Custom App editor
instead of keeping the repository-backed absolute `include:` wrapper. Relative
bind sources such as `./config/prometheus.xml` were therefore resolved from the
TrueNAS-generated application directory. When the relative source was missing,
Docker could create a directory at that source path, producing an invalid bind
mount for ClickHouse.

### Recovery

Keep the Custom App wrapper minimal:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/clickhouse/compose.yml
```

Then recreate the ClickHouse app/container from the repository Compose and
verify both the host source and container target are regular files.

### Guard

`scripts/truenas/audit-app-lifecycle.sh` verifies that
`/etc/clickhouse-server/config.d/prometheus.xml` is a regular file whenever
ClickHouse is running.

## 2. The ClickHouse bootstrap user could not delegate privileges

### Symptom

Granting the Langfuse migration privilege failed even though
`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` was enabled.

### Root cause

Access management being enabled does not prove that the effective bootstrap
identity can delegate every privilege. The administrative `clickhouse` account
must itself expose the required grant option.

### Diagnosis

Always inspect effective grants before creating or modifying service accounts:

```sql
SHOW GRANTS FOR clickhouse;
```

The expected administrative contract includes:

```text
GRANT ALL ON *.* WITH GRANT OPTION
```

### Guard

The runtime audit fails explicitly when the `clickhouse` identity cannot prove
`WITH GRANT OPTION`.

## 3. Langfuse 4.30.0 migration 48 failed with Code 497

### Symptom

Langfuse reached ClickHouse migration 48 and failed on:

```sql
ALTER TABLE scores
MODIFY SETTING
  enable_block_number_column = 1,
  enable_block_offset_column = 1;
```

ClickHouse returned Code 497 because the dedicated `langfuse` identity lacked
`ALTER SETTINGS`. Subsequent starts reported:

```text
Dirty database version 48
```

### Root cause

The earlier Langfuse grant set covered table, column, index, mutation, and
system-table access, but not database-scoped MergeTree setting changes.

### Recovery

Grant the missing privilege with the administrative ClickHouse identity:

```sql
GRANT ALTER SETTINGS ON langfuse.* TO langfuse;
```

For this deployment the Langfuse ClickHouse history is disposable. Stop
Langfuse, add the grant, then drop and recreate only the `langfuse` database so
migrations restart cleanly from version 1. Do not force migration 48 clean and
do not delete the shared `/mnt/cpool/clickhouse` datastore.

### Guard

The runtime audit checks `SHOW GRANTS FOR langfuse` and fails unless
database-scoped `ALTER SETTINGS ON langfuse.*` is present.

## 4. ClickHouse datastore ownership blocked destructive DDL

### Symptom

Destructive ClickHouse operations could fail with a filesystem permission error
below:

```text
/var/lib/clickhouse/store
```

### Root cause

Recovered files could retain ownership from another UID, including historical
TrueNAS application ownership, while the current ClickHouse container runs as
UID/GID 101.

### Recovery

During a maintenance window for all shared ClickHouse consumers, stop
ClickHouse after confirming no other container mounts the datastore, then repair
ownership:

```bash
sudo chown -R 101:101 /mnt/cpool/clickhouse
sudo chown -R 101:101 /mnt/cpool/logs/clickhouse-server
```

Creating the top-level directory with `install -d` does not recursively repair
existing files.

## 5. A healthy ClickHouse ping is necessary but not sufficient

```bash
curl -fsS http://172.17.0.24:8123/ping
```

returning `Ok.` proves the HTTP listener, but not the complete shared-service
contract. After recovery also validate:

- authenticated SQL execution and the expected ClickHouse version/timezone;
- the `clickhouse` administrative delegation contract;
- the dedicated `langfuse` database/user and migration grants;
- Langfuse web database health and worker health;
- Sentry/Snuba health before considering the shared ClickHouse recovery closed.

Future ClickHouse consumers such as ntopng must receive a dedicated
database/user contract and must be added to the same compatibility gate rather
than reusing the administrative `clickhouse` identity.

## Regression policy

The incident is considered closed only when the repository audit and contract
tests prove all of the following:

```text
prometheus.xml regular-file mount
+ ClickHouse HTTP/SQL runtime
+ clickhouse WITH GRANT OPTION
+ langfuse dedicated database/user
+ ALTER SETTINGS ON langfuse.*
+ Langfuse web/worker health
+ shared-consumer health
```
