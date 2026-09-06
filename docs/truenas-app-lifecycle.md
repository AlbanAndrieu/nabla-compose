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

## Fresh Langfuse v4 reset

The previous Langfuse v3 state is intentionally not migrated. Langfuse v4 is
installed as a fresh deployment so the dirty ClickHouse migration marker can be
discarded instead of repaired.

Target versions and dependencies:

- Langfuse web/worker: `4.30.0`;
- ClickHouse: `26.8.2.7` on a fresh `cpool/clickhouse` dataset;
- PostgreSQL: existing shared server, but a new dedicated database/user named
  `langfuse`;
- Redis: existing shared service on `redis:6379`, isolated with
  `REDIS_KEY_PREFIX=langfuse-v4:`;
- MinIO: existing shared service on `minio:9000`, isolated in bucket
  `langfuse-v4`.

Langfuse v4 requires ClickHouse >=25.12, PostgreSQL >=15 and Redis >=7. The
selected ClickHouse version is a current LTS release and the Langfuse containers
are pinned to the stable v4.30.0 release.

### 1. Keep rollback copies, do not delete the old state

Stop Langfuse before resetting any dependency:

```bash
midclt call app.stop langfuse
```

Keep the existing ClickHouse snapshot and rename the old dataset instead of
destroying it:

```bash
zfs snapshot -r cpool/clickhouse@pre-langfuse-v4-reset-$(date +%Y%m%d)

zfs rename \
  cpool/clickhouse \
  cpool/clickhouse-v3-backup

zfs create cpool/clickhouse

mkdir -p /mnt/cpool/logs/clickhouse-server
chown -R 101:101 /mnt/cpool/clickhouse /mnt/cpool/logs/clickhouse-server
chmod 770 /mnt/cpool/clickhouse /mnt/cpool/logs/clickhouse-server
```

Do not destroy `cpool/clickhouse-v3-backup` until Langfuse v4 has passed its
validation window.

### 2. Create a dedicated ClickHouse secret

The ClickHouse application reads only the password from:

```text
/mnt/cpool/clickhouse/.env.secrets
```

Create a new password and mirror the same value into the Langfuse runtime secret
file without printing it:

```bash
umask 077
CLICKHOUSE_PASSWORD="$(openssl rand -hex 32)"

printf 'CLICKHOUSE_PASSWORD=%s\n' "${CLICKHOUSE_PASSWORD}" |
  tee /mnt/cpool/clickhouse/.env.secrets >/dev/null

sed -i '/^CLICKHOUSE_PASSWORD=/d' /mnt/cpool/langfuse/.env.secrets
printf 'CLICKHOUSE_PASSWORD=%s\n' "${CLICKHOUSE_PASSWORD}" |
  tee -a /mnt/cpool/langfuse/.env.secrets >/dev/null

chmod 600 \
  /mnt/cpool/clickhouse/.env.secrets \
  /mnt/cpool/langfuse/.env.secrets

unset CLICKHOUSE_PASSWORD
```

The repository Compose fixes the non-secret identity to:

```text
CLICKHOUSE_USER=clickhouse
CLICKHOUSE_DB=langfuse
```

### 3. Create a fresh PostgreSQL database/user

Do not reuse the former `postgres` database. Create a dedicated role and
database on the existing PostgreSQL service:

```bash
LANGFUSE_DB_PASSWORD="$(openssl rand -hex 32)"

docker exec -u postgres postgres psql \
  -v ON_ERROR_STOP=1 \
  --set=langfuse_password="${LANGFUSE_DB_PASSWORD}" \
  -c "DROP DATABASE IF EXISTS langfuse;" \
  -c "DROP ROLE IF EXISTS langfuse;" \
  -c "CREATE ROLE langfuse LOGIN PASSWORD :'langfuse_password';" \
  -c "CREATE DATABASE langfuse OWNER langfuse;"
```

Replace the old `DATABASE_URL` in the runtime secret file:

```bash
sed -i '/^DATABASE_URL=/d;/^DIRECT_URL=/d' \
  /mnt/cpool/langfuse/.env.secrets

printf 'DATABASE_URL=postgresql://langfuse:%s@172.17.0.24:5432/langfuse\n' \
  "${LANGFUSE_DB_PASSWORD}" |
  tee -a /mnt/cpool/langfuse/.env.secrets >/dev/null

printf 'DIRECT_URL=postgresql://langfuse:%s@172.17.0.24:5432/langfuse\n' \
  "${LANGFUSE_DB_PASSWORD}" |
  tee -a /mnt/cpool/langfuse/.env.secrets >/dev/null

chmod 600 /mnt/cpool/langfuse/.env.secrets
unset LANGFUSE_DB_PASSWORD
```

### 4. Isolate the shared Redis and MinIO dependencies

Host ports and container ports are different contracts. Langfuse must use
`redis:6379` and `minio:9000` over `intranet`.

The v4 Compose sets:

```text
REDIS_KEY_PREFIX=langfuse-v4:
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse-v4
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET=langfuse-v4
LANGFUSE_S3_BATCH_EXPORT_BUCKET=langfuse-v4
```

This prevents v4 BullMQ/cache keys from colliding with stale v3 Redis keys and
keeps new S3 objects separate from the previous deployment.

Create the bucket before starting Langfuse. Use the existing MinIO credentials
without printing them:

```bash
docker exec minio sh -lc '
  mkdir -p /data/langfuse-v4
'
```

Then verify shared service discovery:

```bash
docker exec mongo getent hosts redis
docker exec mongo getent hosts minio
docker exec mongo getent hosts clickhouse
```

### 5. Redeploy ClickHouse first

Pull the branch/merged revision and recreate ClickHouse from the repository
Compose. The new container must join `intranet` with alias `clickhouse`.

After startup:

```bash
curl -fsS http://172.17.0.24:8123/ping &&
  echo "ClickHouse HTTP OK"

docker exec mongo \
  bash -lc 'timeout 3 bash -c "</dev/tcp/clickhouse/9000"' &&
  echo "ClickHouse TCP migration endpoint OK"

docker exec clickhouse clickhouse-client \
  --query 'SELECT version(), timezone(), currentDatabase()'
```

The timezone must remain `UTC`.

### 6. Redeploy Langfuse v4

The Compose uses the shared dependencies through:

```text
CLICKHOUSE_MIGRATION_URL=clickhouse://clickhouse:9000
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_DB=langfuse
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_KEY_PREFIX=langfuse-v4:
```

Secrets such as `DATABASE_URL`, `DIRECT_URL`, `CLICKHOUSE_PASSWORD`,
`REDIS_AUTH`, `SALT`, `ENCRYPTION_KEY`, `NEXTAUTH_SECRET` and S3
credentials remain in `/mnt/cpool/langfuse/.env.secrets`.

For a fresh v4 deployment, remove partial headless-initialization variables
unless the full bootstrap set is intentionally configured. Do not carry only a
subset of `LANGFUSE_INIT_*` variables from the previous deployment.

Redeploy Langfuse and follow both containers:

```bash
midclt call app.redeploy langfuse

docker logs --tail=200 -f ix-langfuse-langfuse-web-1
docker logs --tail=200 -f ix-langfuse-langfuse-worker-1
```

### 7. Validate v4 before removing rollback data

```bash
curl -fsS \
  'http://172.17.0.24:3000/api/public/health?failIfDatabaseUnavailable=true' |
  jq

curl -fsS http://127.0.0.1:3030/api/health | jq

scripts/truenas/audit-app-lifecycle.sh
```

Keep `cpool/clickhouse-v3-backup` and the pre-reset snapshot until the web and
worker remain healthy and a new Langfuse project can ingest/query test traces.

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
