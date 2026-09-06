# ntopng

The service captures the host interface configured by `NTOPNG_INTERFACE` and
uses the existing shared ClickHouse server for historical flows.

The ClickHouse integration requires an **ntopng Enterprise M or higher**
license. Do not enable the ClickHouse flow backend until the required ntopng
license is installed and validated.

## Dedicated ClickHouse identity

ntopng must not reuse the shared administrative `clickhouse` account or the
ClickHouse `default` user. The runtime contract is intentionally fixed to:

```text
host     = 172.17.0.24 (override with CLICKHOUSE_HOST only when reviewed)
database = ntopng
user     = ntopng
password = NTOPNG_CLICKHOUSE_PASSWORD from /mnt/cpool/ntopng/.env.secrets
```

Create a dedicated database/user with the ClickHouse administrative identity.
A database-scoped bootstrap grant is acceptable because ntopng owns its schema;
never grant this service account global `*.*` privileges:

```sql
CREATE DATABASE IF NOT EXISTS ntopng;
CREATE USER IF NOT EXISTS ntopng IDENTIFIED WITH sha256_password BY '<secret>';
GRANT ALL ON ntopng.* TO ntopng;
```

Generate and store the password outside Git:

```bash
sudo install -d -m 700 /mnt/cpool/ntopng
umask 077
printf 'NTOPNG_CLICKHOUSE_PASSWORD=%s\n' "$(openssl rand -hex 32)" |
  sudo tee /mnt/cpool/ntopng/.env.secrets >/dev/null
sudo chmod 600 /mnt/cpool/ntopng/.env.secrets
```

Use the same password when creating/resetting the ClickHouse `ntopng` user.
Do not print the value during runtime validation.

## Runtime behavior

The repository wrapper constructs ntopng's ClickHouse `-F` option inside the
container from the runtime environment and then delegates to the upstream
`/run.sh` entrypoint. This prevents the password from being embedded in the
repository Compose file or requiring Compose-time secret interpolation.

`--strict-startup` is enabled. If ntopng cannot initialize its ClickHouse
backend, the service must fail startup instead of silently running without
historical flow persistence.

Default ClickHouse target: `172.17.0.24:9000`, database `ntopng`.

Before treating the service as operational, validate:

1. the dedicated `ntopng` database and user exist;
2. the dedicated credentials can execute an authenticated query against
   database `ntopng`;
3. the user has no global `*.*` grant;
4. ntopng remains running with strict startup enabled;
5. new flows appear in ClickHouse and remain queryable after both ntopng and
   ClickHouse restarts.

The lifecycle audit performs the first four checks when the TrueNAS ntopng app
is running. Flow persistence remains an explicit runtime acceptance test.
