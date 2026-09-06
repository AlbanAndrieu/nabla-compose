# TrueNAS application lifecycle recovery

This runbook reconciles repository-backed Compose applications with the
TrueNAS Apps runtime without giving public CI access to the private homelab.

## Custom App include contract

Repository applications are installed as independent TrueNAS Custom Apps with
a minimal configuration:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/<app>/compose.yml
```

Cross-application dependencies must use shared external Docker networks.
`depends_on` is valid only for services defined in the same Compose project.

The shared backend network is:

```text
intranet
```

Create it once if it does not already exist:

```bash
docker network inspect intranet >/dev/null 2>&1 ||
  docker network create --driver bridge intranet
```

## Runtime inventory

Run the read-only audit:

```bash
scripts/truenas/audit-app-lifecycle.sh
```

It compares every tracked `apps/*/compose.yml` with `midclt app.query` and
also reports Docker containers that are restarting, unhealthy, exited or dead.
This is necessary because an app can be reported `RUNNING` while one of its
containers is restarting.

## Bichon

Bichon is pinned to 2.0.3 and keeps its existing dataset:

```text
/mnt/cpool/bichon -> /data
```

The directory is expected to remain writable by UID/GID 568. The required
encryption password stays outside Git:

```text
/mnt/cpool/bichon/.env.secrets
BICHON_ENCRYPT_PASSWORD=<stable secret>
```

Validate the secret without printing it:

```bash
grep -q '^BICHON_ENCRYPT_PASSWORD=.' /mnt/cpool/bichon/.env.secrets
```

Do not rotate this value casually after Bichon has encrypted stored account
credentials.

When a v1.x dataset is detected by Bichon 2.x, stop every container using the
dataset, snapshot it, then run the non-destructive Fjall migration:

```bash
zfs snapshot -r cpool/bichon@pre-bichon-v2-migration-$(date +%Y%m%d)

docker run --rm -it \
  --user 568:568 \
  --env-file /mnt/cpool/bichon/.env.secrets \
  -e BICHON_ROOT_DIR=/data \
  -v /mnt/cpool/bichon:/data \
  --entrypoint bichon-admin \
  rustmailer/bichon:2.0.3
```

Select **Migrate v1.x Storage to v2.x (Fjall -> bichon-blob)** for an existing
v1.x deployment. Do not select the v0.3.7 migration unless the source really is
the legacy v0.3.7 layout. Restart Bichon only after the admin migration reports
success.

HTTP health is not sufficient when Bichon logs a recurring OAuth2 decryption
failure. Compare the current encryption password with the pre-migration
snapshot without printing either value. If they differ, recover the original
secret before allowing token refreshes. If they match, keep the data snapshot and use the Bichon UI for the affected
account: open **OAuth2 Tokens**, choose **Delete Token** for the unusable token,
then repeat the OAuth2 authorization flow. Do not edit encrypted token records
directly.

## Shared MongoDB then Graylog

MongoDB is a standalone reusable application in `apps/mongo`. Graylog no
longer embeds MongoDB and connects to it over `intranet`.

Prepare storage:

```bash
mkdir -p /mnt/cpool/mongo/data /mnt/cpool/graylog/data/journal
chown -R 999:999 /mnt/cpool/mongo/data
chown -R 1100:1100 /mnt/cpool/graylog/data/journal
chmod 770 /mnt/cpool/mongo/data /mnt/cpool/graylog/data/journal
```

Create MongoDB credentials:

```bash
umask 077
MONGO_PASSWORD="$(openssl rand -hex 32)"
cat > /mnt/cpool/mongo/.env.secrets <<EOF
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD}
EOF
chmod 600 /mnt/cpool/mongo/.env.secrets
```

Keeping `root` as the MongoDB bootstrap administrator is supported. Prefer a
dedicated Graylog database user after MongoDB is healthy:

```bash
MONGO_ROOT_PASSWORD="$(
  sed -n 's/^MONGO_INITDB_ROOT_PASSWORD=//p' /mnt/cpool/mongo/.env.secrets
)"
GRAYLOG_MONGO_PASSWORD="$(openssl rand -hex 32)"

docker exec \
  -e GRAYLOG_MONGO_PASSWORD="${GRAYLOG_MONGO_PASSWORD}" \
  mongo mongosh --quiet \
  -u root -p "${MONGO_ROOT_PASSWORD}" --authenticationDatabase admin \
  --eval '
const graylog = db.getSiblingDB("graylog");
const roles = [
  { role: "readWrite", db: "graylog" },
  { role: "dbAdmin", db: "graylog" },
  { role: "clusterMonitor", db: "admin" }
];
const password = process.env.GRAYLOG_MONGO_PASSWORD;
if (graylog.getUser("graylog")) {
  graylog.updateUser("graylog", { pwd: password, roles });
} else {
  graylog.createUser({ user: "graylog", pwd: password, roles });
}
'
```

Then populate the existing Graylog secret file without committing either
secret:

```bash
MONGO_PASSWORD="${GRAYLOG_MONGO_PASSWORD}"
GRAYLOG_PASSWORD_SECRET="$(openssl rand -hex 48)"
read -r -s -p 'Graylog admin password: ' GRAYLOG_ADMIN_PASSWORD
printf '\n'
GRAYLOG_ROOT_PASSWORD_SHA2="$(
  printf '%s' "${GRAYLOG_ADMIN_PASSWORD}" | sha256sum | awk '{print $1}'
)"
cat > /mnt/cpool/graylog/.env.secrets <<EOF
GRAYLOG_PASSWORD_SECRET=${GRAYLOG_PASSWORD_SECRET}
GRAYLOG_ROOT_PASSWORD_SHA2=${GRAYLOG_ROOT_PASSWORD_SHA2}
GRAYLOG_MONGODB_URI=mongodb://graylog:${MONGO_PASSWORD}@mongo:27017/graylog?authSource=graylog
EOF
chmod 600 /mnt/cpool/graylog/.env.secrets
unset MONGO_PASSWORD MONGO_ROOT_PASSWORD GRAYLOG_MONGO_PASSWORD
unset GRAYLOG_PASSWORD_SECRET GRAYLOG_ADMIN_PASSWORD GRAYLOG_ROOT_PASSWORD_SHA2
```

Before redeploying, validate the secret contract without printing either value:

```bash
sudo awk -F= '
  $1 == "GRAYLOG_PASSWORD_SECRET" {
    value = substr($0, index($0, "=") + 1)
    printf "GRAYLOG_PASSWORD_SECRET length=%d\n", length(value)
  }
  $1 == "GRAYLOG_ROOT_PASSWORD_SHA2" {
    value = substr($0, index($0, "=") + 1)
    printf "GRAYLOG_ROOT_PASSWORD_SHA2 length=%d\n", length(value)
  }
' /mnt/cpool/graylog/.env.secrets
```

`GRAYLOG_PASSWORD_SECRET` must be at least 16 effective characters and
`GRAYLOG_ROOT_PASSWORD_SHA2` must be a 64-character hexadecimal SHA-256
digest. Matching outer single/double quotes in an env file are syntax, not part
of the effective secret value; a raw length of 17 can therefore represent only
15 effective characters.

Before replacing `GRAYLOG_PASSWORD_SECRET`, inspect whether the target Graylog
MongoDB database already contains application collections. When reusing an
existing Graylog database, preserve the historical `GRAYLOG_PASSWORD_SECRET`
if it can be recovered; changing it can make previously encrypted Graylog
settings unreadable.

If the Graylog database is genuinely empty because this is a new migration
target that has never booted successfully, generate a new high-entropy password
secret (96 hexadecimal characters is sufficient) and normalize any matching
outer quotes around `GRAYLOG_ROOT_PASSWORD_SHA2`. Do not print either value.

Graylog keeps port `9000` inside the container but defaults to host port
`9003` because ClickHouse already publishes host TCP/9000. Verify TCP/9003 is
free before the first start.

The Graylog Docker image already provides its runtime configuration under
`/usr/share/graylog/data/config`. Do not bind-mount the whole host
`/mnt/cpool/graylog/data` over `/usr/share/graylog/data`, and do not mount
an empty repository config directory over `/usr/share/graylog/data/config`:
either case hides the image-provided `graylog.conf` and produces
`Couldn't open properties file`. The repository therefore persists only
`/usr/share/graylog/data/journal`; Graylog settings are supplied through
environment variables and the image configuration.

Install/start in this order:

1. `mongo`;
2. existing `opensearch` application;
3. `graylog`.

Graylog 6.3.x is intentionally kept on the existing OpenSearch 2.19.5 backend.

## OpenRAG

OpenRAG and Langflow must not declare Compose `depends_on` entries for
services belonging to separate TrueNAS apps.

The runtime path is:

```text
OpenRAG backend --intranet--> Langflow:7860
       |
       +-----------intranet--> OpenSearch:9200
```

The OpenSearch application publishes the service-name alias `opensearch` on
`intranet`.

Create the secret files expected by the two applications:

```text
/mnt/cpool/openrag/.env.secrets
/mnt/cpool/langflow/.env.secrets
```

At minimum both need the password matching the existing OpenSearch primary
cluster:

```text
OPENSEARCH_PASSWORD=<existing OpenSearch password>
```

Langflow is deployed with interactive authentication enabled, so
`/mnt/cpool/langflow/.env.secrets` must additionally contain a strong
bootstrap superuser password:

```text
LANGFLOW_SUPERUSER_PASSWORD=<strong random password>
```

Generate it without printing it:

```bash
grep -q '^LANGFLOW_SUPERUSER_PASSWORD=.' /mnt/cpool/langflow/.env.secrets || {
  printf 'LANGFLOW_SUPERUSER_PASSWORD=%s\n' "$(openssl rand -hex 32)" |
    sudo tee -a /mnt/cpool/langflow/.env.secrets >/dev/null
}
sudo chmod 600 /mnt/cpool/langflow/.env.secrets
```

The primary OpenSearch container must be recreated from the repository Compose
after the `intranet` migration so that the `opensearch` network alias is
actually attached at runtime. A Compose file declaring the alias does not
retroactively modify an already-running container.

Start/recreate `opensearch`, validate `opensearch:9200` from `intranet`,
then start `langflow`, then `openrag`.

Langflow telemetry is disabled declaratively with `DO_NOT_TRACK=true`.

## Gatus

The repository Gatus instance persists status history in:

```text
/mnt/cpool/gatus/gatus.db
```

The generated configuration owns the SQLite storage declaration so regenerating
service consumers does not accidentally remove persistence.

## InfluxDB and Scrutiny

Follow `apps/influxdb/README.md`. InfluxDB must be healthy on
`127.0.0.1:31055` before restarting the standalone Scrutiny service.

Scrutiny receives only its sensitive InfluxDB token from:

```text
/mnt/cpool/scrutiny/.env.secrets
```

with:

```text
SCRUTINY_WEB_INFLUXDB_TOKEN=<dedicated restricted token>
```

The Compose definition declares the recovered non-secret datastore identity
directly:

```text
SCRUTINY_WEB_INFLUXDB_ORG=nabla
SCRUTINY_WEB_INFLUXDB_BUCKET=metrics
```

These values may still be overridden through Compose interpolation, but a
repository-local `apps/scrutiny/.env` is not required for the TrueNAS Custom
App deployment.

For the current recovered InfluxDB datastore, the organization is `nabla`.
Do not guess the Scrutiny bucket. Locate the bucket that actually contains
Scrutiny's `smart` or `temp` measurements before creating the final token.
If no existing bucket contains those measurements, create a new dedicated
`metrics` (or `scrutiny`) bucket and accept that there is no Scrutiny history
in this InfluxDB datastore.

The recovery/operator token is only for administration; do not reuse it for
Scrutiny. In particular, `nabla's Recovery Token` is a temporary recovery
credential and must not be stored as `SCRUTINY_WEB_INFLUXDB_TOKEN`.
Scrutiny's bring-your-own-InfluxDB mode needs the base bucket plus
three downsampling buckets (`<base>_weekly`, `<base>_monthly`,
`<base>_yearly`) and the three corresponding aggregation tasks. Its restricted
application token needs read access to the organization plus scoped read/write
access to those buckets and tasks.

If no historical Scrutiny bucket is found, use the upstream default base name
`metrics`, create the four placeholder buckets and three placeholder tasks,
then create the restricted token. Scrutiny replaces the placeholder task
configuration during startup.

## Langfuse shared Redis and MinIO

Host ports and container ports are different contracts. Redis publishes
`30059:6379` and MinIO publishes `9002:9000`, but Langfuse should use
`redis:6379` and `minio:9000` only after both services have joined the
external `intranet` network.

Validate the network rather than testing host DNS:

```bash
docker network inspect intranet |
  jq -r '.[0].Containers[]?.Name' |
  sort

docker exec mongo getent hosts redis
docker exec mongo getent hosts minio
docker exec mongo bash -lc 'timeout 3 bash -c "</dev/tcp/redis/6379"'
docker exec influxdb curl -fsS http://minio:9000/minio/health/live
```

The host command `ping minio` is not evidence for Docker service discovery;
host DNS may resolve a public search-domain hostname instead.

Before replacing the current TrueNAS Langfuse app, materialize its current
runtime secrets into `/mnt/cpool/langfuse/.env.secrets` without printing them.
The existing TrueNAS application already has these variables in its rendered
container environment; creating a new dataset does not copy them automatically.

```bash
sudo install -d -m 700 /mnt/cpool/langfuse

{
  sudo docker inspect ix-langfuse-langfuse-worker-1 \
    --format '{{range .Config.Env}}{{println .}}{{end}}'
  sudo docker inspect ix-langfuse-langfuse-web-1 \
    --format '{{range .Config.Env}}{{println .}}{{end}}'
} |
  grep -E '^(DATABASE_URL|SALT|ENCRYPTION_KEY|CLICKHOUSE_PASSWORD|LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID|LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY|LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID|LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY|LANGFUSE_S3_BATCH_EXPORT_ACCESS_KEY_ID|LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY|REDIS_AUTH|SMTP_CONNECTION_URL|NEXTAUTH_SECRET|LANGFUSE_INIT_PROJECT_SECRET_KEY|LANGFUSE_INIT_USER_PASSWORD)=' |
  awk -F= '!seen[$1]++' |
  sudo tee /mnt/cpool/langfuse/.env.secrets >/dev/null

sudo chmod 600 /mnt/cpool/langfuse/.env.secrets
sudo sed 's/=.*$/=<redacted>/' /mnt/cpool/langfuse/.env.secrets
```

The final command prints variable names only. Keep the existing TrueNAS
Langfuse application available for rollback until the Compose-backed web and
worker containers both remain stable.

The repository Compose no longer contains production-like fallback passwords.

## Fresh Langfuse v4 reset

The previous Langfuse state is disposable. Use a fresh Langfuse v4
initialization instead of repairing the former v3/v4 ClickHouse migration
marker.

Shared infrastructure contracts:

- ClickHouse: `26.8.2.7`, timezone `UTC`, dedicated user/database
  `langfuse`;
- PostgreSQL: shared PostgreSQL 18.6 with dedicated role/database `langfuse`;
- shared administrative/generic identities (`clickhouse`, `nabla`) remain
  separate from Langfuse runtime credentials;
- the ClickHouse bootstrap administrator enables SQL-driven access management via
  `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1`; this is required to create and alter
  dedicated service users such as `langfuse`;
- Redis: internal `redis:6379`, key prefix `langfuse-v4:`;
- MinIO: internal `minio:9000`, bucket `langfuse-v4`.

Runtime secrets remain in:

```text
/mnt/cpool/langfuse/.env.secrets
```

and must include at least:

```text
DATABASE_URL=postgresql://langfuse:<secret>@172.17.0.24:5432/langfuse
CLICKHOUSE_PASSWORD=<dedicated Langfuse ClickHouse password>
REDIS_AUTH=<shared Redis password>
SALT=<stable Langfuse salt>
ENCRYPTION_KEY=<stable Langfuse encryption key>
NEXTAUTH_SECRET=<stable NextAuth secret>
```

The ClickHouse service is shared infrastructure. Never delete
`/mnt/cpool/clickhouse` merely to reset Langfuse. Reset only the dedicated
ClickHouse database `langfuse`.

Before the reset, confirm ClickHouse itself:

```bash
docker exec ix-clickhouse-clickhouse-1 sh -c '
clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --query "SELECT version(), timezone(), currentDatabase()"
'
```

Expected current live values are `26.8.2.7`, `UTC`, and `default`.

If destructive ClickHouse DDL fails with `filesystem_error:
Permission denied` below `/var/lib/clickhouse/store`, stop Langfuse and plan a
short maintenance window for every shared ClickHouse consumer. Confirm that no
other container mounts `/mnt/cpool/clickhouse`, stop ClickHouse, then repair
the inherited ownership before restarting it:

```bash
sudo chown -R 101:101 /mnt/cpool/clickhouse
sudo chown -R 101:101 /mnt/cpool/logs/clickhouse-server
```

`sudo install -d -o 101 -g 101 -m 0750 /mnt/cpool/clickhouse` creates the
directory if it is missing and applies owner/mode; it does **not** erase an
existing datastore. It does not replace the recursive ownership repair when old
files are already owned by UID 568 or root.

After ClickHouse is healthy again, create a dedicated Langfuse database/user
with the administrative `clickhouse` identity. Generate a high-entropy
`LANGFUSE_CLICKHOUSE_PASSWORD`, keep it outside Git, and store the same value
as `CLICKHOUSE_PASSWORD` in `/mnt/cpool/langfuse/.env.secrets`.

Required Langfuse v4 permissions for the single-container server:

```sql
CREATE DATABASE IF NOT EXISTS langfuse;
CREATE USER IF NOT EXISTS langfuse IDENTIFIED WITH sha256_password BY '<secret>';

GRANT SELECT, INSERT ON langfuse.* TO langfuse;
GRANT ALTER UPDATE, ALTER DELETE ON langfuse.* TO langfuse;
GRANT CREATE, DROP TABLE, DROP VIEW ON langfuse.* TO langfuse;
GRANT ALTER ADD COLUMN, ALTER MODIFY COLUMN, ALTER VIEW MODIFY QUERY ON langfuse.* TO langfuse;
GRANT ALTER ADD INDEX, ALTER DROP INDEX, ALTER MATERIALIZE INDEX ON langfuse.* TO langfuse;

GRANT SELECT(database, table, name, partition, partition_id, active, rows)
  ON system.parts TO langfuse;
GRANT SELECT(database, table, is_done)
  ON system.mutations TO langfuse;
GRANT SELECT(database, name, engine)
  ON system.tables TO langfuse;
GRANT SELECT ON system.processes TO langfuse;
GRANT SELECT ON system.query_log* TO langfuse;

GRANT SYSTEM SYNC REPLICA, SYSTEM MERGES, ALTER SETTINGS
  ON langfuse.observations_pid_tid_sorting TO langfuse;
```

Keep `CLICKHOUSE_CLUSTER_ENABLED=false` on this single-container deployment;
the clustered `REMOTE` and `CLUSTER` grants are therefore unnecessary.

PostgreSQL is also isolated. Do not modify the existing `nabla` role. Create a
dedicated role/database and place its URL in the Langfuse secret file:

```sql
CREATE ROLE langfuse LOGIN PASSWORD '<secret>';
CREATE DATABASE langfuse OWNER langfuse;
```

```text
DATABASE_URL=postgresql://langfuse:<secret>@172.17.0.24:5432/langfuse
```

The generic `nabla` role and shared `postgres` database remain untouched.

The v4 Compose isolates the other shared dependencies with:

```text
CLICKHOUSE_MIGRATION_URL=clickhouse://clickhouse:9000
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_DB=langfuse
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_KEY_PREFIX=langfuse-v4:
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse-v4
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET=langfuse-v4
LANGFUSE_S3_BATCH_EXPORT_BUCKET=langfuse-v4
```

Before starting Langfuse v4:

1. verify Docker DNS and TCP/9000 for `clickhouse`;
2. verify Redis TCP/6379 and MinIO HTTP/9000;
3. verify PostgreSQL user `langfuse` can connect to database `langfuse`;
4. verify ClickHouse user `langfuse` can access database `langfuse` while
   the administrative `clickhouse` identity remains separate;
5. ensure no stale partial `LANGFUSE_INIT_*` bootstrap variables remain unless
   the complete headless bootstrap set is intentionally configured.

Redeploy Langfuse and validate:

```bash
curl -fsS \
  'http://172.17.0.24:3000/api/public/health?failIfDatabaseUnavailable=true'

curl -fsS http://127.0.0.1:3030/api/health
```

A fresh smoke-test trace must be ingestible and queryable before the reset is
considered complete.

Because ClickHouse is shared, also validate Sentry/Snuba after the change.
Sentry self-hosted upstream still vendors an Altinity ClickHouse 25.8 baseline;
if synthetic Sentry event ingestion/search fails against the shared 26.8.2.7
server, decouple Sentry onto its own vendor-supported ClickHouse. When ntopng is
enabled later, validate its dedicated `ntopng` database and flow persistence.


## Homarr permissions

Homarr runs with `PUID=568` and `PGID=568`. Its entrypoint creates/chowns
`/appdata` and nginx runtime directories before dropping privileges. The
Compose file therefore drops every Linux capability and adds back only
`CHOWN`, `DAC_OVERRIDE`, `SETGID`, and `SETUID`. `DAC_OVERRIDE` is
required so the root startup process can traverse/chown nginx directories after
all default Docker capabilities have been dropped.

Prepare the existing dataset before recreation:

```bash
chown -R 568:568 /mnt/cpool/homarr
chmod -R u+rwX,g+rwX /mnt/cpool/homarr
```

Homarr v1.x requires the variable name `SECRET_ENCRYPTION_KEY`. If the
existing file still uses the legacy/local name `HOMARR_ENCRYPTION_KEY`, rename
the variable without changing its value:

```bash
if grep -q '^HOMARR_ENCRYPTION_KEY=.' /mnt/cpool/homarr/.env.secrets &&
  ! grep -q '^SECRET_ENCRYPTION_KEY=.' /mnt/cpool/homarr/.env.secrets; then
  sed -i 's/^HOMARR_ENCRYPTION_KEY=/SECRET_ENCRYPTION_KEY=/' \
    /mnt/cpool/homarr/.env.secrets
fi
chmod 600 /mnt/cpool/homarr/.env.secrets
```

Do not rotate the key: stored integration secrets depend on the original
`SECRET_ENCRYPTION_KEY`.

## Historical TrueNAS lifecycle failures

Historical errors for Prometheus duplicate YAML keys, mutually-exclusive
`network_mode`/networks settings, obsolete pfSense exporter images and the
old Code Server `security_opt` shape are not present in the current Compose
definitions.

Karakeep Chrome and Paperless Tika should only be changed when their current
healthchecks fail. A historical unhealthy start followed by a healthy current
container is treated as a recovered transient incident, not as a reason to
weaken healthchecks.
