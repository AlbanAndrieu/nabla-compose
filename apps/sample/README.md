# FastAPI Sample on TrueNAS

`apps/sample/compose.yml` runs the `fastapi-sample` repository locally on TrueNAS while keeping runtime secrets outside Git.

## Prerequisites

- Initialize the repository submodule used as the Docker build context:

  ```bash
  git submodule update --init --recursive fastapi-sample
  ```

- Bootstrap the shared backend network once if it does not already exist, and verify the Traefik network created by the TrueNAS Traefik app:

  ```bash
  docker network inspect intranet >/dev/null 2>&1 || docker network create --driver bridge intranet
  docker network inspect traefik_network >/dev/null
  ```

  `intranet` is the shared backend/service-discovery network used by multiple independent Compose projects. Keep it separate from `traefik_network`, which is the ingress/proxy network.

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

## Prometheus / core health metrics

FastAPI Sample can optionally enrich the service-first health board from the
existing Prometheus recording-rule contract without exposing arbitrary PromQL.

Put the non-secret Prometheus endpoint in `/mnt/cpool/sample/.env`:

```dotenv
HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090
HOMELAB_PROMETHEUS_TIMEOUT_SECONDS=1.5
```

The application only reads the fixed `nabla:*` recording rules maintained in
`apps/prometheus/rules/nabla-core.rules.yml`. The current summary covers
TrueNAS CPU/memory capacity plus TrueNAS, cAdvisor, pfSense and Prometheus
telemetry availability.

Prometheus telemetry is diagnostic evidence, not the authoritative service
outcome. If Prometheus or an exporter is unavailable, FastAPI Sample must report
telemetry as unavailable/degraded without marking the underlying service or
platform down.

Keep this endpoint on the trusted LAN. Do not publish Prometheus merely to make
the FastAPI Cloud health board richer.

## Supabase

If by “Sybase” you mean **Supabase**, no local Supabase stack is currently defined in `nabla-compose`. FastAPI Sample can consume an existing Supabase project through the same `.env.secrets` file, for example:

```dotenv
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=REPLACE_WITH_SERVICE_ROLE_KEY
SUPABASE_PUBLISHABLE_KEY=REPLACE_WITH_PUBLISHABLE_KEY
```

Optional PostgreSQL/Supavisor settings (`POSTGRES_*`, `SUPABASE_PROJECT_REF`, `SUPABASE_POOLER_REGION`) can also be supplied when direct database access is required. Do not add a local database container only to satisfy optional health checks.

## Validate and deploy

Validate the manifests without expanding runtime secrets:

```bash
docker compose --project-directory apps/redis -f apps/redis/compose.yml config --quiet --no-interpolate --no-env-resolution
docker compose --project-directory apps/sample -f apps/sample/compose.yml config --quiet --no-interpolate --no-env-resolution
```

Avoid pasting the output of a fully interpolated `docker compose config` command into tickets or chats because it can expand values from local environment files.

Then deploy from the repository root:

```bash
docker compose -f apps/sample/compose.yml up -d --build
```

The local host port defaults to `8091`, mapped to container port `8080`:

```bash
curl -fsS http://127.0.0.1:8091/health
```

The internal Traefik route remains `https://fastapi-sample.int.albandrieu.com`.
The public route is `https://sample.albandrieu.com`.

### Public ingress ownership

Keep responsibilities separated:

```text
AutoXpose (Cloudflare DNS only)
        |
        v
sample.albandrieu.com -> 82.66.4.247
        |
        v
pfSense HAProxy :443
        | TLS re-encryption
        v
Traefik :443
        |
        v
fastapi-sample:8080
```

AutoXpose must have the Cloudflare DNS provider configured for
`albandrieu.com` and **no Nginx Proxy Manager or Caddy proxy provider**.
The sample uses `autoxpose.enable=auto`, so configuring a proxy provider in
AutoXpose would create a second proxy route and violate this ownership model.

The legacy `docker-traefik-cloudflare-companion` still runs for other Traefik
hosts. It is explicitly configured to exclude the `sample` and `int`
subdomain trees from the `albandrieu.com` zone so it cannot race AutoXpose
for `sample.albandrieu.com` or publish private `*.int.albandrieu.com`
routers to public DNS. Long term, consolidate Cloudflare record ownership into
one reconciler instead of keeping multiple DNS automation paths.

Current AutoXpose labels intentionally use only the documented contract:
`autoxpose.enable`, `subdomain`, `name`, `scheme` and `port`.
Do not reintroduce the legacy/unsupported `autoxpose.domain` label.

AutoXpose targets the published host port `8091` for discovery/DNS metadata;
Traefik reaches the container directly on `traefik_network` port `8080`.

### TLS / DNS acceptance

Traefik uses Let's Encrypt with the Cloudflare DNS-01 challenge. Keep the ACME
registration email explicit via `TRAEFIK_ACME_EMAIL`. The certificate store is
`/mnt/cpool/traefik/certs/acme.json`; it must exist with mode `600` and must
not be shared by multiple Traefik instances.

Run the read-only acceptance check from TrueNAS **or from a LAN workstation**
after recreating AutoXpose, Traefik and FastAPI Sample:

```bash
bash scripts/ingress/verify-sample-exposure.sh
```

The defaults target the TrueNAS runtime at `172.17.0.24`:

- FastAPI Sample: `http://172.17.0.24:8091/health`;
- AutoXpose: `http://172.17.0.24:4949`;
- Traefik TLS: `172.17.0.24:443`.

A workstation-local FastAPI process listening on `0.0.0.0:8080` is a
different runtime. To test it deliberately, override only the local probe:

```bash
LOCAL_HEALTH_URL=http://127.0.0.1:8080/health \
  bash scripts/ingress/verify-sample-exposure.sh
```

When the script runs outside TrueNAS, the direct `acme.json` filesystem check
is skipped if `/mnt/cpool/traefik/certs/acme.json` is not readable; both live
TLS certificate checks still run.

The script verifies the local health endpoint, AutoXpose Cloudflare DNS-only
ownership, public DNS, the certificate served directly by Traefik with SNI,
the public certificate served by pfSense/HAProxy, and the final public
`/health` path.


## Persistence policy

Do not mount the FastAPI source tree or an application-data directory into the production container unless a future feature introduces real local state. If that happens, create a dedicated TrueNAS dataset for that state and document its ownership, backup and restore policy separately.
