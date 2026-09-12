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

Use a unique password and store only the runtime password in:

```text
/mnt/cpool/joplin/.env.secrets
```

with root ownership and mode `0600`:

```dotenv
POSTGRES_PASSWORD=<dedicated Joplin database password>
```

The resulting SQL state must be equivalent to:

```sql
CREATE ROLE joplin LOGIN PASSWORD '<dedicated password>';
CREATE DATABASE joplin OWNER joplin;
```

Do not reuse the PostgreSQL superuser password or another application's role.

## Deploy

```bash
cd /mnt/cpool/compose/nabla-compose

sudo install -d -m 0700 /mnt/cpool/joplin
sudo chmod 0600 /mnt/cpool/joplin/.env.secrets

sudo midclt call -j app.update joplin \
  "$(jq -cn --arg include '/mnt/cpool/compose/nabla-compose/apps/joplin/compose.yml' \
    '{custom_compose_config:{include:[$include]}}')"

sudo midclt call -j app.redeploy joplin
```

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
