# PostgreSQL exporter

Prometheus exporter for the shared native TrueNAS PostgreSQL App (`postgres`).
It is its own Custom App, `postgres-exporter`, so its status and lifecycle never
mix with the database App.

## Monitoring role

A login role that is only a member of the predefined `pg_monitor` role. Run as
the PostgreSQL administrator in the shared PostgreSQL container; `\password`
hashes the password client-side, so it never reaches logs or shell history:

```sql
CREATE ROLE postgres_exporter LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3;
GRANT pg_monitor TO postgres_exporter;
\password postgres_exporter
```

## Runtime secret

`/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets` (`root:root 0600`)
holds only `DATA_SOURCE_NAME`, rendered from the Vaultwarden item
`nabla/prod/postgres-exporter` (`config/secrets/manifest.json`):

```text
DATA_SOURCE_NAME=postgresql://postgres_exporter:REDACTED@172.17.0.24:5432/postgres?sslmode=require
```

The exporter uses `lib/pq`, which rejects `sslmode=prefer`. Since 12/11/2026
the server runs TLS 1.3, so `require` encrypts the connection. `verify-full`
needs the CA mounted; that mount lives under `/mnt/cpool/secrets` and counts
as secret debt until the public CA moves out of it.

## Activation

In the change that deploys the App:

- remove `status: planned` from `compose.yml` and set
  `albandrieu.com/operational-state: active` in `catalog-info.yaml`;
- remove `operational_state: planned` from the `postgres_exporter` job in
  `apps/prometheus/prometheus.yml`;
- add `postgres-exporter` to `config/truenas/custom-apps.yml`.

Check with `sudo bash scripts/truenas/diagnose-postgres-exporter.sh`, then
`up{job="postgres_exporter"} == 1` and `pg_up == 1`.
