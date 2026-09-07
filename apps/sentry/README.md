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
- ClickHouse: `clickhouse:9000` / `:8123`, dedicated database and users.

Kafka, Memcached, Snuba, Relay, Taskbroker, and NGINX remain scoped to the
Sentry Custom App.

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
containing only the one-shot migration credentials:

```dotenv
CLICKHOUSE_PASSWORD=
CLICKHOUSE_READONLY_PASSWORD=
CLICKHOUSE_TRACE_PASSWORD=
```

These values belong to `sentry_migrator` and must not be copied into the
runtime `.env.secrets` file.

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
`WITH GRANT OPTION` and without any global `*.*` privilege. The runtime
identity should remain narrower.

Initial runtime contract:

```sql
GRANT SELECT, INSERT, ALTER UPDATE, ALTER DELETE ON sentry.* TO sentry;
GRANT SELECT ON system.tables TO sentry;
```

Bootstrap compatibility contract:

```sql
GRANT ALL ON sentry.* TO sentry_migrator;
GRANT SELECT ON system.tables TO sentry_migrator;
```

The database-scoped `ALL` is deliberately isolated to the short-lived
migration identity. After the first successful Snuba bootstrap, inspect the
effective migration queries and narrow the migrator grants if possible.

Never grant either Sentry identity `ALL ON *.*` or `WITH GRANT OPTION`.

## ClickHouse compatibility gate

Sentry self-hosted 26.8.0 is not shipped against the homelab's shared
ClickHouse 26.8.2.7. Treat this integration as a compatibility test.

The acceptance gate is not an HTTP listener check. It requires:

1. `snuba-migrate` exits 0;
2. Snuba authenticates as `sentry` against database `sentry`;
3. the Sentry ClickHouse schema contains tables;
4. Relay, Kafka, Sentry consumers, and Snuba consumers stay healthy;
5. a synthetic SDK event is accepted and becomes queryable through Sentry.

If Snuba bootstrap or normal queries fail because of ClickHouse version
incompatibility, do **not** downgrade or reset the shared ClickHouse datastore.
Move Sentry to a dedicated ClickHouse version supported by that Sentry release.

## TrueNAS Custom App

The persistent TrueNAS configuration should remain a small absolute include:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/sentry/compose.yml
```

The repository file is therefore the only Compose source of truth.

Apply the wrapper with `app.update` while the app is stopped whenever the
stored TrueNAS configuration needs repair.

## First deployment

Before deployment:

```bash
install -d -m 700 \
  /mnt/cpool/sentry \
  /mnt/cpool/sentry/data \
  /mnt/cpool/sentry/kafka \
  /mnt/cpool/sentry/relay \
  /mnt/cpool/sentry/taskbroker

chmod 600 /mnt/cpool/sentry/.env.secrets /mnt/cpool/sentry/.env.migrator.secrets
```

Validate the repository Compose before asking TrueNAS to start it:

```bash
docker compose \
  -f apps/sentry/compose.yml \
  config --quiet
```

Then use the TrueNAS lifecycle:

```bash
sudo midclt call -j app.stop sentry
sudo midclt call -j app.start sentry
```

Do not remove ClickHouse, PostgreSQL, or Redis data as part of a Sentry
deployment.

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
