# ntopng

The service captures the host interface configured by `NTOPNG_INTERFACE` and
uses the existing shared ClickHouse server for historical flows.

The ClickHouse integration requires an **ntopng Enterprise M or higher**
license. Do not enable the ClickHouse flow backend until the required ntopng
license is installed and validated.

The TrueNAS app mounts the persistent license from
`/mnt/cpool/ntopng/ntopng.license` with `create_host_path: false`. The
deployment therefore fails instead of allowing Docker to create a directory
when the expected license file is missing. If a legacy host license already
exists at `/etc/ntopng.license`, migrate it without printing its contents:

```bash
sudo install -d -m 700 /mnt/cpool/ntopng
if sudo test -f /etc/ntopng.license; then
  sudo install -m 600 /etc/ntopng.license /mnt/cpool/ntopng/ntopng.license
fi
sudo test -s /mnt/cpool/ntopng/ntopng.license
```

Otherwise place the licensed file directly at the persistent path with mode
`0600` before creating the TrueNAS app.

## Dedicated ClickHouse identity

ntopng must not reuse the shared administrative `clickhouse` account or the
ClickHouse `default` user. The runtime contract is intentionally fixed to:

```text
host     = 172.17.0.24 (override with CLICKHOUSE_HOST only when reviewed)
database = ntopng
user     = ntopng
password = NTOPNG_CLICKHOUSE_PASSWORD from /mnt/cpool/ntopng/.env.secrets
           mounted as /run/secrets/ntopng_runtime_env
```

Create a dedicated database/user with the ClickHouse administrative identity.
Grant only the database-scoped DML/DDL that ntopng actually uses. The upstream
schema creates tables/views, applies ALTER migrations, and the maintenance
paths can truncate data. Do not grant `ALL`, global `*.*`, access-management,
or administrative privileges to this service account:

```sql
CREATE DATABASE IF NOT EXISTS ntopng;
CREATE USER IF NOT EXISTS ntopng IDENTIFIED WITH sha256_password BY '<secret>';

-- Runtime DML plus explicit maintenance/purge support.
GRANT SELECT, INSERT, TRUNCATE ON ntopng.* TO ntopng;

-- ntopng bootstraps tables/views and applies schema migrations at startup.
-- CREATE TABLE includes CREATE VIEW; DROP TABLE includes DROP VIEW.
GRANT CREATE TABLE, DROP TABLE, ALTER ON ntopng.* TO ntopng;
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
Keep this dedicated credential exactly 64 hexadecimal characters. This matches
`openssl rand -hex 32` and allows the runtime wrapper to decode the
Vaultwarden-rendered outer dotenv quotes without evaluating the secret file as
shell code. Do not print the value during runtime validation.

## Runtime behavior

The host `.env.secrets` file is mounted with the Compose secrets mechanism as
`/run/secrets/ntopng_runtime_env`; it is **not** injected through `env_file`.
The wrapper extracts `NTOPNG_CLICKHOUSE_PASSWORD`, renders
`/run/nabla-ntopng.conf` at container startup with mode `0600`, then
delegates to the upstream `/run.sh` entrypoint using only that
configuration-file path. The ClickHouse password is therefore absent from the
repository, Compose interpolation, Docker `Config.Env`, and the ntopng process
command line. The wrapper also unsets its local password variable before
starting ntopng, leaving the ephemeral root-readable configuration file as the
runtime credential carrier.

The generated configuration enables `--strict-startup`. If ntopng cannot
initialize its ClickHouse backend, the service must fail startup instead of
silently running without historical flow persistence.

Default ClickHouse target: `172.17.0.24:9000`, database `ntopng`.

Before treating the service as operational, validate:

1. the dedicated `ntopng` database and user exist;
2. the dedicated credentials can execute an authenticated query against
   database `ntopng`;
3. Docker `Config.Env` does not contain `NTOPNG_CLICKHOUSE_PASSWORD`;
4. the user has the required database-scoped DML/DDL grants but neither
   `ALL ON ntopng.*` nor any global `*.*` grant;
5. the mounted license is a regular non-empty file and `ntopng -V` reports
   Enterprise M/L/XL/XXL;
6. ntopng remains running with strict startup enabled;
7. new flows appear in ClickHouse and remain queryable after both ntopng and
   ClickHouse restarts.

The lifecycle audit performs the first four checks when the TrueNAS ntopng app
is running. Flow persistence remains an explicit runtime acceptance test.
