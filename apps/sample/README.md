# FastAPI Sample on TrueNAS

`apps/sample/compose.yml` runs the `fastapi-sample` repository locally on TrueNAS while keeping runtime secrets outside Git.

## Prerequisites

- Initialize the repository submodule used as the Docker build context:

  ```bash
  git submodule update --init --recursive fastapi-sample
  ```

- Ensure the shared external Docker networks already exist:

  ```bash
  docker network inspect intranet >/dev/null
  docker network inspect traefik_network >/dev/null
  ```

- Deploy Redis from `apps/redis/compose.yml` (or another Redis service attached to `intranet` with the DNS alias `redis`) before enabling the optional Redis integration.

## TrueNAS configuration dataset

FastAPI Sample is currently treated as stateless. It does **not** need a dedicated application-data volume. Redis already persists its own data in `/mnt/cpool/redis`.

Use `/mnt/cpool/sample` only as a small configuration/secrets dataset or directory:

```bash
mkdir -p /mnt/cpool/sample
chmod 700 /mnt/cpool/sample
```

Create `/mnt/cpool/sample/.env` for non-secret runtime settings and `/mnt/cpool/sample/.env.secrets` for credentials. Do not commit either file.

Example Redis configuration in `.env.secrets`:

```dotenv
REDIS_URL=redis://:REPLACE_WITH_REDIS_PASSWORD@redis:6379/0
```

There is deliberately no Compose `depends_on` from FastAPI Sample to Redis because they are separate Compose projects. Service discovery is provided by the shared external `intranet` network.

## Supabase

If by “Sybase” you mean **Supabase**, no local Supabase stack is currently defined in `nabla-compose`. FastAPI Sample can consume an existing Supabase project through the same `.env.secrets` file, for example:

```dotenv
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=REPLACE_WITH_SERVICE_ROLE_KEY
SUPABASE_PUBLISHABLE_KEY=REPLACE_WITH_PUBLISHABLE_KEY
```

Optional PostgreSQL/Supavisor settings (`POSTGRES_*`, `SUPABASE_PROJECT_REF`, `SUPABASE_POOLER_REGION`) can also be supplied when direct database access is required. Do not add a local database container only to satisfy optional health checks.

## Validate and deploy

Validate the manifest without starting the stack:

```bash
docker compose -f apps/sample/compose.yml config
```

Then deploy from the repository root:

```bash
docker compose -f apps/sample/compose.yml up -d --build
```

The local host port defaults to `8091`, mapped to container port `8080`:

```bash
curl -fsS http://127.0.0.1:8091/health
```

The Traefik route is `https://fastapi-sample.int.albandrieu.com` when the `traefik_network` and internal DNS/TLS configuration are available.

## Persistence policy

Do not mount the FastAPI source tree or an application-data directory into the production container unless a future feature introduces real local state. If that happens, create a dedicated TrueNAS dataset for that state and document its ownership, backup and restore policy separately.
