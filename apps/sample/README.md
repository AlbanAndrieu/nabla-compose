# FastAPI Sample on TrueNAS

`apps/sample/compose.yml` runs the `fastapi-sample` repository locally on TrueNAS while keeping runtime secrets outside Git.

## Prerequisites

- Initialize the repository submodule used as the Docker build context:

  ```bash
  git submodule update --init --recursive fastapi-sample
  ```

- Bootstrap the shared backend network once if it does not already exist, and verify the Traefik network created by the TrueNAS Traefik app:

  ```bash
  docker network inspect intranet >/dev/null 2>&1 || \
    docker network create --driver bridge --subnet 172.16.55.0/24 intranet
  docker network inspect traefik_network >/dev/null
  ```

  `intranet` is the shared backend/service-discovery network used by multiple independent Compose projects. Keep it separate from `traefik_network`, which is the ingress/proxy network. The current production network uses `172.16.55.0/24`; do not recreate it with a different subnet without reviewing every static address and TrueNAS source-allowlist dependency.

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

The internal Traefik route is `https://sample.int.albandrieu.com`.
It is intentionally the only `Host(...)` router for this container because the
current Pi-hole synchronizer extracts one hostname per Docker container.

The protected public route is `https://sample.albandrieu.com`.

### Ingress ownership

Keep the LAN and public ingress paths separate:

```text
LAN workstation
      |
      v
Pi-hole DNS
sample.int.albandrieu.com -> 172.17.0.24
      |
      v
Traefik :443
      |
      v
fastapi-sample:8080
```

```text
Internet
   |
   v
Cloudflare Access
   |
   v
Cloudflare Tunnel
   |
   v
http://172.17.0.24:8091
   |
   v
fastapi-sample:8080
```

For the Cloudflare Tunnel published application, use:

- public hostname: `sample.albandrieu.com`;
- service type: `HTTP`;
- service URL: `http://172.17.0.24:8091`.

The public Tunnel path deliberately bypasses pfSense HAProxy and Traefik.
Cloudflare Tunnel establishes the origin connection outbound from the
`cloudflared` connector, so there is no reason to publish the sample through
the WAN HAProxy path as well.

The account uses a Default-Deny Cloudflare Access posture. Therefore the
hostname also needs a matching self-hosted Access application with at least
one effective policy. A Tunnel route alone is not enough: without an Access
application/policy, Cloudflare correctly blocks the request before it reaches
the origin.

Do not add AutoXpose labels to FastAPI Sample. AutoXpose may keep its persisted
Nginx Proxy Manager provider for other services, but it is not an owner of
either Sample hostname:

- `sample.int.albandrieu.com` -> Pi-hole / Traefik;
- `sample.albandrieu.com` -> Cloudflare Tunnel / Access.

### TLS / Access acceptance

Run the read-only acceptance check from TrueNAS or from a LAN workstation:

```bash
bash scripts/ingress/verify-sample-exposure.sh
```

The TrueNAS deployment sets `FASTAPI_RUNTIME_MODE=homelab`, so the API landing
page identifies this runtime as **TrueNAS homelab production** rather than a
local workstation. This mode is distinct from FastAPI Cloud production and is
intended to use trusted LAN paths for TrueNAS, pfSense and Prometheus observers.

The Compose service also applies container-local split DNS for the appliance
hostnames:

```text
truenas.albandrieu.com -> 172.17.0.24
home.albandrieu.com    -> 172.17.0.1
```

This keeps the existing TLS hostnames and certificate verification while
bypassing public/WAN DNS routing from the internal observer. Keep
`TRUENAS_API_VERIFY_SSL=true` and `PFSENSE_API_VERIFY_SSL=true` when the
appliance certificates validate those hostnames. Do not replace this with
`verify=false` merely to use a private IP.

### TrueNAS WebSocket source allowlist

TrueNAS 26.0.0-BETA.2 applies `system.general.ui_allowlist` to API/UI
WebSocket source addresses **before API-key authentication**. The WebSocket
handler checks the active runtime value returned by
`system.general.get_ui_allowlist`, not merely the persisted value visible in
`system.general.config`. Those values can temporarily differ during
update/restart/rollback/check-in handling. A successful `GET /api/versions`
therefore proves HTTPS reachability only; it does not prove that
`/api/current` is permitted.

For the Docker-hosted observer, TrueNAS sees the FastAPI container address on
the shared `intranet` bridge, not the TrueNAS LAN address. A policy close such
as:

```text
WebSocket connection closed with code=1008
You are not allowed to access this resource
```

is a source-address allowlist denial, not an `APPS_READ` RBAC failure.

The live 2026-09-06 recovery proved the sequence:

```text
/api/versions over HTTPS                         -> HTTP 200
native BETA.2 midclt as fastapi_observer         -> system.version + app.query succeed
FastAPI container before ui_allowlist change     -> WebSocket denied
allow container intranet IP /32                  -> system.version + app.query = 86
system.general.checkin                           -> change persisted
```

Run the read-only preflight after every recreate/network change:

```bash
scripts/security/verify-truenas-observer-access.sh
```

Do not allow the whole shared Docker subnet merely to make this observer work.
The Compose service pins the observer source to
`${FASTAPI_SAMPLE_OBSERVER_IP:-172.16.55.9}` on `intranet`, matching the
reviewed TrueNAS `/32` allowlist entry. A collision or subnet mismatch should
fail deployment rather than silently move the observer to a different source
address. Override `FASTAPI_SAMPLE_OBSERVER_IP` only together with a reviewed
TrueNAS allowlist update. A future dedicated observer network can isolate this
boundary further.

The canonical runtime credentials are:

```dotenv
TRUENAS_API_USERNAME=fastapi_observer
TRUENAS_API_KEY=<dedicated user-linked API key>
```

Remove stale `TRUENAS_USER` / `TRUENAS_USERNAME` aliases from the TrueNAS
FastAPI runtime once migration is proven. The application intentionally prefers
`TRUENAS_API_USERNAME`, but leaving an old alias creates a dangerous fallback:
if the canonical variable disappears later, the old username could be paired
with the new canonical API key.

For Prometheus, keep the existing LAN-only setting in
`/mnt/cpool/sample/.env`:

```dotenv
HOMELAB_PROMETHEUS_URL=http://172.17.0.24:9090
```

The defaults target the TrueNAS runtime at `172.17.0.24` and validate:

1. direct FastAPI health on `http://172.17.0.24:8091/health`;
2. Pi-hole resolution of `sample.int.albandrieu.com` to `172.17.0.24`;
3. direct Traefik routing/TLS for the internal hostname;
4. public Cloudflare DNS and edge TLS;
5. Cloudflare Access enforcement.

Without a Cloudflare Access service token, a redirect/challenge from Access is
the expected public result. To prove the full Tunnel path through Access, set
both service-token variables:

```bash
CF_ACCESS_CLIENT_ID='...' \
CF_ACCESS_CLIENT_SECRET='...' \
  bash scripts/ingress/verify-sample-exposure.sh
```

The script then sends the standard Cloudflare Access service-token headers and
requires `https://sample.albandrieu.com/health` to return successfully.

A workstation-local FastAPI process listening on `0.0.0.0:8080` is a
different runtime. To test it deliberately, override only the direct health
probe:

```bash
LOCAL_HEALTH_URL=http://127.0.0.1:8080/health \
  bash scripts/ingress/verify-sample-exposure.sh
```


## Persistence policy

Do not mount the FastAPI source tree or an application-data directory into the production container unless a future feature introduces real local state. If that happens, create a dedicated TrueNAS dataset for that state and document its ownership, backup and restore policy separately.
