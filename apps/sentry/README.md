# Sentry on TrueNAS

`apps/sentry/compose.yml` is the runtime source of truth for the TrueNAS
Custom App named `sentry`. Do not deploy the repository submodule
`sentry/`; it is not part of this lifecycle.

## Runtime profile

The stack is pinned to Sentry self-hosted 26.8.0 and intentionally starts with
the `errors-only` profile. It keeps the Sentry ingestion/query path intact:

```text
client / SDK
  -> nginx
  -> Relay
  -> Kafka
  -> Sentry ingest consumer
  -> Snuba consumer
  -> ClickHouse

Sentry web
  -> Snuba API
  -> ClickHouse
```

The homelab shares infrastructure where the product supports explicit external
configuration:

- PostgreSQL: `172.17.0.24:5432`, dedicated database/role `sentry`;
- Redis: `redis:6379` on the external `intranet` network, dedicated DB 3;
- ClickHouse: dedicated `sentry-clickhouse:9000` instance from `apps/sentry-clickhouse/compose.yml`, pinned to the Sentry 26.8.0 upstream-supported Altinity 25.3 line;
- Kafka: shared `kafka:9092` broker from `apps/kafka/compose.yml`.

Memcached, Snuba, Relay, Taskbroker, and NGINX remain scoped to the Sentry
Custom App. Kafka has its own TrueNAS lifecycle and must be healthy before
Sentry is started or migrated.

## Secrets

Create `/mnt/cpool/sentry/.env.secrets` with mode `0600`. The file must not
be committed.

Required names:

```dotenv
SENTRY_SECRET_KEY=
SENTRY_DB_PASSWORD=
SENTRY_REDIS_PASSWORD=
REDIS_PASSWORD=
RELAY_REDIS_URL=
RELAY_ID=
RELAY_PUBLIC_KEY=
RELAY_SECRET_KEY=
CLICKHOUSE_PASSWORD=
CLICKHOUSE_READONLY_PASSWORD=
CLICKHOUSE_TRACE_PASSWORD=
```

The three runtime ClickHouse password variables currently refer to the same
dedicated runtime identity `sentry`.

Create a second mode-`0600` file, `/mnt/cpool/sentry/.env.migrator.secrets`,
containing only the one-shot ClickHouse migration credentials:

```dotenv
CLICKHOUSE_PASSWORD=
CLICKHOUSE_READONLY_PASSWORD=
CLICKHOUSE_TRACE_PASSWORD=
```

The ClickHouse values belong to `sentry_migrator`. The one-shot
`snuba-migrate` service loads the normal `.env.secrets` first and the
migrator file second, so the shared `REDIS_PASSWORD` is reused without being
duplicated while the three ClickHouse passwords are overridden by the
restricted migrator identity. None of the migrator ClickHouse credentials
must be copied into the runtime `.env.secrets` file.

`RELAY_REDIS_URL` must reference the shared authenticated Redis service. Do
not print this URL in diagnostics because it contains the Redis password.

Relay 26.8 accepts `RELAY_ID`, `RELAY_PUBLIC_KEY`, and `RELAY_SECRET_KEY`
directly. Generate them once and keep them in the secret file; do not depend on
the repository `sentry/` submodule or an ephemeral Relay credentials file.

## ClickHouse identities

Create the database before starting Sentry because Snuba opens its configured
database during bootstrap:

```sql
CREATE DATABASE IF NOT EXISTS sentry;
```

Use two identities:

- `sentry_migrator`: schema migration identity, used only by
  `snuba-migrate`;
- `sentry`: long-running Snuba API/consumer identity.

The migration identity may be granted broad privileges **only inside**
`sentry.*` during the compatibility/bootstrap phase, without
`WITH GRANT OPTION`. The only global privileges allowed are the explicitly
required `CREATE WORKLOAD` and `DROP WORKLOAD` rights on `*.*`; `ALL ON *.*`
remains forbidden. The runtime identity should remain narrower.

Initial runtime contract:

```sql
GRANT SELECT, INSERT, ALTER UPDATE, ALTER DELETE ON sentry.* TO sentry;
GRANT SELECT ON system.tables TO sentry;
```

Bootstrap compatibility contract:

```sql
GRANT ALL ON sentry.* TO sentry_migrator;
GRANT SELECT ON system.tables TO sentry_migrator;
GRANT SELECT ON system.replicas TO sentry_migrator;
GRANT SELECT ON system.columns TO sentry_migrator;
GRANT CREATE WORKLOAD, DROP WORKLOAD ON *.* TO sentry_migrator;
```

If a Snuba bootstrap is interrupted after a migration has been marked
`IN PROGRESS`, do not edit Snuba's migration tracking tables manually. Use
the native recovery flow scoped to the affected migration group:

```bash
snuba migrations reverse-in-progress \
  --group events_analytics_platform \
  --dry-run

snuba migrations reverse-in-progress \
  --group events_analytics_platform
```

For migration `0052_create_deletes_workload`, the reverse operations are
`DROP WORKLOAD IF EXISTS low_priority_deletes` and
`DROP WORKLOAD IF EXISTS all`, so recovering from a failure before or during
workload creation is idempotent. Rerun `snuba bootstrap --force` only after the
migration status is back to `NOT_STARTED`.

The database-scoped `ALL` is deliberately isolated to the short-lived
migration identity. After the first successful Snuba bootstrap, inspect the
effective migration queries and narrow the migrator grants if possible.

Never grant either Sentry identity `ALL ON *.*` or `WITH GRANT OPTION`.

## Bootstrap incident log — 2026-09-07

The first Sentry 26.8 bootstrap uncovered several distinct failure modes. Keep
them separate when troubleshooting; each has a different remediation.

1. **Shared ClickHouse 26.8.2.7 incompatible with Snuba 26.8 migrations.**
   Snuba reached `generic_metrics:0041_adjust_partitioning_meta_tables`, where
   ClickHouse 26.x rejected an `AggregatingMergeTree` layout unless
   `allow_dimensions_outside_sorting_key=1` is enabled. We deliberately did
   not enable that compatibility setting globally. Sentry was moved to the
   upstream-supported Altinity ClickHouse
   `25.3.6.10034.altinitystable` compatibility bridge.
2. **Dedicated ClickHouse config unreadable.**
   The worktree file `apps/sentry-clickhouse/config.xml` inherited mode
   `0600`, so ClickHouse failed before opening TCP/9000 with
   `Access to file denied`. The Compose definition now uses `configs:` rather
   than a direct bind mount so checkout file permissions cannot reproduce this
   failure.
3. **Snuba metadata reads denied.**
   Bootstrap required `SELECT` on `system.tables`, `system.replicas`, and
   `system.columns` for the short-lived `sentry_migrator` identity. These are
   explicitly granted without widening the runtime `sentry` user.
4. **Snuba workload DDL denied.**
   Migration `events_analytics_platform:0052_create_deletes_workload` required
   `CREATE WORKLOAD ON *.*`; migration `0053` uses
   `CREATE OR REPLACE WORKLOAD` and therefore also requires
   `DROP WORKLOAD ON *.*`. Only these two global workload privileges are
   granted to `sentry_migrator`; `ALL ON *.*` remains forbidden.
5. **Migration left IN PROGRESS after privilege failure.**
   After `0052` failed, a plain bootstrap rerun stopped with
   `MigrationInProgress`. Recovery used the native Snuba command
   `migrations reverse-in-progress --group events_analytics_platform`, whose
   rollback for `0052` is idempotent
   (`DROP WORKLOAD IF EXISTS low_priority_deletes`; `DROP WORKLOAD IF EXISTS all`).
   Manual edits of migration tracking state are forbidden.
6. **Legacy PostgreSQL migration graph blocked Sentry 26.8 upgrade.**
   The first `sentry upgrade --noinput --create-kafka-topics` reached Django
   migration planning but failed while constructing `ProjectState` with lazy
   references such as `feedback.Feedback.environment -> sentry.environment`
   and the message `app 'sentry' isn't installed`. PostgreSQL inspection then
   proved that the supposedly disposable Sentry database was not fresh: it held
   273 public tables and 687 `django_migrations` rows, including 469 `sentry`
   migrations, with the latest migration wave dated 2026-08-03. Upstream Sentry
   26.8 includes `sentry` in `INSTALLED_APPS`, so this was an incompatible
   legacy migration history rather than a missing Django app. Because the old
   Sentry instance was explicitly empty/disposable, recovery was a targeted
   drop/recreate of database `sentry` owned by role `sentry`; no other
   PostgreSQL database was changed and no code-level `INSTALLED_APPS` workaround
   was introduced.
7. **Fresh PostgreSQL migration validated.**
   After recreating only database `sentry`, `sentry upgrade --noinput
   --create-kafka-topics` completed with exit code 0. The fresh schema contains
   323 public tables and 490 Django migration rows; no `Traceback`,
   `InconsistentMigrationHistory`, permission error or PostgreSQL fatal error
   remained. Sentry created its internal project successfully and shared Kafka
   contained 87 topics after the migration.
8. **Taskbroker could not resolve shared Kafka.**
   The first full runtime start showed `taskbroker` restarting with
   `Failed to resolve 'kafka:9092'`. The service had been attached only to the
   Sentry-internal network even though shared Kafka lives on external
   `intranet`. Taskbroker must join both networks: `sentry` for the Sentry
   taskworker RPC path and `intranet` for Kafka. The taskworker gRPC
   `connection refused` / `no route to host` messages were a downstream
   symptom of Taskbroker restart-looping.
9. **NGINX host port requested but not activated on an internal-only network.**
   The first full runtime start showed NGINX healthy internally and
   `HostConfig.PortBindings` requesting `172.17.0.24:9005 -> 80/tcp`, while
   `NetworkSettings.Ports["80/tcp"]` was null, `docker port` returned
   nothing, and host curls were refused. The container was attached only to the
   project network declared with `internal: true`. NGINX now joins external
   `intranet` with `gw_priority: 1` and keeps the `sentry` network for
   service-to-service routing. Runtime acceptance requires the active Docker
   port mapping in `NetworkSettings.Ports`, not merely the requested
   `HostConfig.PortBindings`. On TrueNAS/Docker in this deployment, `docker port`
   may still print nothing even when `NetworkSettings.Ports` contains the active
   mapping and the host HTTP probe succeeds, so `docker port` is not used as the
   acceptance source of truth.
10. **Validated outcome.**
   After the scoped grants and native recovery flow, `snuba bootstrap --force`
   completed successfully with exit code 0 against
   `sentry-clickhouse:9000`. The `sentry` database contains 85 tables and the
   ClickHouse workloads `all` and `low_priority_deletes` exist.

## ClickHouse compatibility gate

Runtime testing proved that Snuba 26.8.0 cannot complete its migrations on the homelab shared ClickHouse 26.8.2.7 without enabling a new ClickHouse 26.x MergeTree compatibility setting globally. Sentry therefore uses a dedicated ClickHouse pinned to the exact Altinity line used by upstream self-hosted 26.8.0. The shared ClickHouse remains untouched for Langfuse and other consumers.

The acceptance gate is not an HTTP listener check. It requires:

1. `snuba-migrate` exits 0;
2. Snuba authenticates as `sentry` against database `sentry`;
3. the Sentry ClickHouse schema contains tables;
4. Relay, Kafka, Sentry consumers, and Snuba consumers stay healthy;
5. a synthetic SDK event is accepted and becomes queryable through Sentry.

Do **not** point Sentry back at the shared ClickHouse 26.8.x datastore unless a future Snuba release explicitly supports that version and the full migration/ingestion/query gate is re-run.

## TrueNAS Custom App

The persistent TrueNAS configuration should remain a small absolute include:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/sentry/compose.yml
```

The repository file is therefore the only Compose source of truth.

Apply the wrapper with `app.update` while the app is stopped whenever the
stored TrueNAS configuration needs repair.

For a TrueNAS Custom App, `app.query` with
`extra.retrieve_config=true` returns the **parsed Compose mapping itself** in
`.config`; it does not echo the API input field
`custom_compose_config_string`. Verify an include wrapper with:

```bash
sudo midclt call app.query \
  '[["id","=","sentry"]]' \
  '{"extra":{"retrieve_config":true}}' |
jq -r '.[0].config.include[]?'
```

During PR validation this should point at the PR worktree. After merge, update
the wrapper back to the canonical
`/mnt/cpool/compose/nabla-compose/apps/sentry/compose.yml` path before
removing the worktree.

## First deployment

Before deployment:

```bash
install -d -m 700 \
  /mnt/cpool/sentry \
  /mnt/cpool/sentry/data \
  /mnt/cpool/sentry/taskbroker

chmod 600 /mnt/cpool/sentry/.env.secrets /mnt/cpool/sentry/.env.migrator.secrets
```

Validate the repository Compose before asking TrueNAS to start it:

```bash
docker compose \
  -f apps/sentry/compose.yml \
  config --quiet
```

Ensure the shared Kafka app is healthy before Sentry:

```bash
sudo midclt call app.query '[["id","=","kafka"]]' |
  jq -r '.[0] | [.id, .state] | @tsv'

sudo docker exec ix-kafka-kafka-1 \
  kafka-topics \
  --bootstrap-server kafka:9092 \
  --list >/dev/null &&
  echo "Kafka API OK"
```

Then use the TrueNAS lifecycle:

```bash
sudo midclt call -j app.stop sentry
sudo midclt call -j app.start sentry
```

Do not remove ClickHouse, PostgreSQL, Redis, or shared Kafka data as part of a Sentry deployment.

## TrueNAS DEPLOYING diagnostic

When Sentry is functionally reachable but TrueNAS still reports the Custom App
as `DEPLOYING`, use the repository read-only diagnostic:

```bash
bash scripts/truenas/diagnose-sentry.sh --check
```

The diagnostic separates:

- TrueNAS `app.query` lifecycle state;
- recent app lifecycle jobs, without printing job arguments;
- steady-state containers from the expected one-shot `snuba-migrate` and
  `sentry-migrate` jobs;
- Docker `starting` / `unhealthy` healthchecks and restart counters;
- Sentry edge health from Snuba API health;
- shared Kafka runtime discovery plus the required error-only topic contract;
- heartbeat file, consumer process and Kafka/Redis/ClickHouse connectivity details
  for unhealthy consumers.

The Sentry 26.8 consumer healthchecks are heartbeat-file based. A container can
be running while Docker health remains `starting`; if TrueNAS is still
`DEPLOYING`, the diagnostic identifies those services without restarting or
redeploying anything. Do not remove the upstream-style healthchecks merely to
make the aggregate state turn green.

Long-running Snuba consumers are ordered after
`sentry-migrate --create-kafka-topics`. The read-only diagnostic verifies
`events`, `event-replacements`, `snuba-commit-log`,
`scheduled-subscriptions-events` and `events-subscription-results` against
the shared Kafka runtime before treating consumer heartbeat failures as an
isolated process-health problem.

## Runtime verification

List the complete Sentry project:

```bash
sudo docker ps -a \
  --filter 'label=com.docker.compose.project=ix-sentry' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

The one-shot jobs must finish successfully:

```bash
sudo docker ps -a \
  --filter 'label=com.docker.compose.project=ix-sentry' \
  --format '{{.Names}}\t{{.Status}}' |
grep -E 'snuba-migrate|sentry-migrate'
```

Check the externally published health endpoint:

```bash
curl -fsS http://172.17.0.24:9005/_health/ && echo
```

Run the repository lifecycle audit after the stack is stable:

```bash
scripts/truenas/audit-app-lifecycle.sh
```

The Sentry/Snuba audit must prove the effective ClickHouse identity
`sentry|sentry` and a non-empty Sentry schema before the compatibility gate is
considered passed.
