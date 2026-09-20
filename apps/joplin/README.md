# Joplin Server on TrueNAS

This directory deploys a private Joplin Server for note synchronization.

## Runtime contract

- image: `joplin/server:3.7.18` by default;
- host port: `172.17.0.24:22300`;
- private URL: `https://joplin.int.albandrieu.com`;
- Docker DNS identity: `joplin:22300`;
- health endpoint: `GET /api/ping`;
- database: shared PostgreSQL on `172.17.0.24:5432`;
- database/user: `joplin` / `joplin`.

The service is deliberately private and must not gain a public Cloudflare `*.int.albandrieu.com` record.

## PostgreSQL bootstrap

Joplin Server does not create an external PostgreSQL role/database. Before first deploy, create a dedicated `joplin` role and database in the shared PostgreSQL instance using the existing PostgreSQL administrative workflow.

Use a unique password. Vaultwarden item `nabla/prod/joplin` in the
`TrueNAS` folder is the source of truth; the canonical root-only runtime
materialization is:

```text
/mnt/cpool/secrets/runtime/joplin/.env.secrets
```

It contains only:

```dotenv
POSTGRES_PASSWORD=<dedicated Joplin database password>
```

The runtime file is a reproducible cache and must remain `root:root 0600`.

The resulting SQL state must be equivalent to:

```sql
CREATE ROLE joplin LOGIN PASSWORD '<dedicated password>';
CREATE DATABASE joplin OWNER joplin;
```

Do not reuse the PostgreSQL superuser password or another application's role.

## Vaultwarden migration and deploy

Keep `BW_SESSION` in the unprivileged operator shell. If an existing Joplin
dotenv is the value source, preview and import it without printing values:

```bash
python scripts/secrets/import_dotenv_to_bitwarden.py --app joplin
python scripts/secrets/import_dotenv_to_bitwarden.py --app joplin --apply
```

If the exact item already exists, review the mapping before deliberately adding
`--update-existing`. For a fresh install with an already-exported
`JOPLIN_POSTGRES_PASSWORD`, use `import_env_to_bitwarden.py --app joplin`
instead.

Materialize the exact Vaultwarden item directly into the canonical root-owned
runtime path without passing `BW_SESSION` through sudo:

```bash
python scripts/secrets/materialize_runtime.py --app joplin --install
python scripts/secrets/materialize_runtime.py --app joplin --verify
```

Then perform the bounded TrueNAS acceptance transaction:

```bash
sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --accept joplin
```

The transaction reconciles the dedicated shared-PostgreSQL role/database,
creates or updates the TrueNAS Custom App, requires stable containers and
`/api/ping`, then finalizes only Joplin's compatible legacy dotenv path.

## Acceptance

```bash
sudo midclt call app.query '[["id","=","joplin"]]' \
  '{"extra":{"retrieve_config":true}}' |
jq '.[0] | {id,state,active_workloads}'

docker ps -a --filter 'name=joplin' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

curl -fsS http://172.17.0.24:22300/api/ping | jq .
curl -kfsS https://joplin.int.albandrieu.com/api/ping | jq .
```

Expected ping payload contains `"status":"ok"` and `"message":"Joplin Server is running"`.

On first login, immediately replace Joplin Server's bootstrap/default administrator credentials. Keep Joplin data in PostgreSQL backups; no separate filesystem storage driver is enabled by this initial deployment.

## Rollback

Stop/remove only the Joplin TrueNAS Custom App. Do not drop the `joplin` PostgreSQL database during normal rollback; retain it until synchronization and restore behavior have been verified and explicit deletion is reviewed.
