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
secret before allowing token refreshes. If they match, keep the data snapshot
and re-authorize the affected OAuth2 account(s) through Bichon rather than
editing encrypted token records directly.

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
Scrutiny. Scrutiny's bring-your-own-InfluxDB mode needs the base bucket plus
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

## Langfuse ClickHouse dirty migration recovery

If Langfuse PostgreSQL migrations are clean but startup reports
`Dirty database version 39`, the failure is in the golang-migrate ClickHouse
state, not PostgreSQL, Redis, or MinIO.

Keep Langfuse stopped and snapshot `cpool/clickhouse` before manipulating the
migration marker. If the marker has already been forced back to version 38,
do not run another `force` command.

Do not guess a migration source directory from the image. Langfuse's own
`clickhouse/scripts/up.sh` selects a delivered migration tree when present,
or renders the canonical migration templates into a temporary directory. This
is the same path used by the application entrypoint and remains valid when a
specific materialized file path is absent from the image.

Use the exact stopped web image and existing runtime secrets:

```bash
LANGFUSE_IMAGE_ID="$(
  docker inspect ix-langfuse-langfuse-web-1 --format '{{.Image}}'
)"

docker run --rm \
  --network host \
  --env-file /mnt/cpool/langfuse/.env.secrets \
  -e CLICKHOUSE_MIGRATION_URL=clickhouse://127.0.0.1:9000 \
  -e CLICKHOUSE_URL=http://127.0.0.1:8123 \
  -e CLICKHOUSE_USER=clickhouse \
  -e CLICKHOUSE_DB=default \
  -e CLICKHOUSE_CLUSTER_ENABLED=false \
  --entrypoint sh \
  "${LANGFUSE_IMAGE_ID}" \
  -lc 'cd /app/packages/shared && sh ./clickhouse/scripts/up.sh'
```

If that command succeeds, restart Langfuse and validate both the web health
endpoint with database checking enabled and the worker health endpoint. If it
fails, retain the snapshot and diagnose that exact migration error; do not
advance the migration marker with another `force`.

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
