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

## Shared MongoDB then Graylog

MongoDB is a standalone reusable application in `apps/mongo`. Graylog no
longer embeds MongoDB and connects to it over `intranet`.

Prepare storage:

```bash
mkdir -p /mnt/cpool/mongo/data /mnt/cpool/graylog/data
chown -R 999:999 /mnt/cpool/mongo/data
chown -R 1100:1100 /mnt/cpool/graylog/data
chmod 770 /mnt/cpool/mongo/data /mnt/cpool/graylog/data
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

docker exec mongo mongosh --quiet \
  -u root -p "${MONGO_ROOT_PASSWORD}" --authenticationDatabase admin \
  --eval "db.getSiblingDB('graylog').createUser({user:'graylog',pwd:'${GRAYLOG_MONGO_PASSWORD}',roles:[{role:'readWrite',db:'graylog'}]})"
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

Start `opensearch`, then `langflow`, then `openrag`.

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

Scrutiny receives its existing InfluxDB identity from:

```text
/mnt/cpool/scrutiny/.env.secrets
```

with the runtime variable names expected by Scrutiny:

```text
SCRUTINY_WEB_INFLUXDB_TOKEN=<dedicated token>
SCRUTINY_WEB_INFLUXDB_ORG=<existing organization>
SCRUTINY_WEB_INFLUXDB_BUCKET=<existing bucket>
```

The Compose definition supplies only `influxdb:8086`; token, organization and
bucket are deliberately not interpolated by Compose.

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
The repository Compose no longer contains production-like fallback passwords.

## Historical TrueNAS lifecycle failures

Historical errors for Prometheus duplicate YAML keys, mutually-exclusive
`network_mode`/networks settings, obsolete pfSense exporter images and the
old Code Server `security_opt` shape are not present in the current Compose
definitions.

Karakeep Chrome and Paperless Tika should only be changed when their current
healthchecks fail. A historical unhealthy start followed by a healthy current
container is treated as a recovered transient incident, not as a reason to
weaken healthchecks.
