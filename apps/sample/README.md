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

## Homelab runtime probes

The TrueNAS Compose deployment intentionally enables the internal observer path:

```yaml
FASTAPI_RUNTIME_MODE: homelab
SICKZ_INTERNAL_NETWORK: "true"
HOMELAB_INTERNAL_PROBES_ENABLED: "true"
PYROSCOPE_SERVER_ADDRESS: http://172.17.0.24:4040
```

Keep these values aligned. `SICKZ_INTERNAL_NETWORK` describes the runtime/network posture, while `HOMELAB_INTERNAL_PROBES_ENABLED` independently enables the LAN service probes. Pyroscope must use the TrueNAS LAN endpoint rather than `localhost:4040`, because `localhost` inside the FastAPI container refers to FastAPI itself.

The health observer is deliberately local-first on the homelab runtime:

- when a catalog service has `external: false`, FastAPI does not schedule a public HTTPS probe for that service; if `internalHost` and `internalPort` exist, the LAN target is probed instead;
- when `external: true`, the public and LAN targets are probed independently; a failed public endpoint with a healthy LAN target is reported as degraded/warning rather than as a locally failed service;
- a stale `tunnelUrl` never overrides `external: false`.

Garage WebUI is the regression example: `external=false`,
`internalHost=172.17.0.24`, `internalPort=3909`, and
`internalSecure=false`.

After deployment, verify the effective runtime without printing unrelated secrets:

```bash
docker exec fastapi-sample env | \
  grep -E '^(FASTAPI_RUNTIME_MODE|SICKZ_INTERNAL_NETWORK|HOMELAB_INTERNAL_PROBES_ENABLED|PYROSCOPE_SERVER_ADDRESS|SENTRY_ENABLED)='
```

For self-hosted Sentry, keep the project DSN in `/mnt/cpool/sample/.env.secrets`. The local Nginx ingress is cleartext HTTP on `172.17.0.24:9005`; TLS, when desired for browser access, terminates on the external/internal reverse proxy rather than that host port.

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


## Update the TrueNAS deployment on port 8091

The `fastapi-sample` source is a Git submodule. The parent repository pins the
exact tested revision; do not advance the submodule locally without also
updating the parent gitlink.

From the canonical TrueNAS checkout:

```bash
cd /mnt/cpool/compose/nabla-compose

git fetch origin
git switch fix/openrag-runtime-diagnostics
git pull --ff-only

git submodule sync --recursive
git submodule update --init --recursive fastapi-sample

printf 'nabla-compose: '
git rev-parse --short HEAD
printf 'fastapi-sample: '
git -C fastapi-sample rev-parse --short HEAD
```

For this recovery branch the expected FastAPI Sample revision is
`3e945146` (release `1.13.2`).

The previous design pinned `172.16.55.9` directly on the shared
`intranet` network. Runtime evidence proved that address was not reserved:
while FastAPI Sample was stopped, Docker assigned `172.16.55.9` to Langflow.
A second attempt with a Compose-managed `172.16.56.0/28` also failed because
that small subnet overlapped a broader Docker/TrueNAS address pool even though
no network used the exact same CIDR.

The repository therefore keeps `sample-observer` external to Compose and
prepares it explicitly after checking **CIDR overlap**, not string equality:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/prepare-sample-observer-network.sh
```

The helper:

- versions the observer-IPAM contract; the current contract is `v2`;
- inspects every Docker network subnet;
- inspects non-default IPv4 host routes so VPN/LAN ranges are not shadowed;
- chooses the first free reviewed private `/28`;
- creates `sample-observer` with an `ip_range` containing six usable
  addresses;
- reserves the nested range's first address (`.8`) plus `.10-.14` with
  Docker `aux-address`, leaving exactly one allocatable container address
  (`.9`); runtime proved Docker can allocate the nested range's first address,
  so it must be reserved explicitly;
- labels the network with `com.nabla.observer-ip=<reserved address>`.

FastAPI Sample does not hard-code that IP. Because it is the only allocatable
address on the dedicated network, Docker reuses it across recreates. The
container remains attached to `intranet` for shared-service DNS and to
`traefik_network` for ingress. `gw_priority: 1` on `sample-observer`
makes the dedicated observer bridge the preferred default route.

If an older `sample-observer` was created before contract `v2`, remove the
failed FastAPI Sample container first and recreate the network explicitly:

```bash
docker rm -f fastapi-sample 2>/dev/null || true

sudo bash scripts/truenas/prepare-sample-observer-network.sh --recreate
```

The helper refuses `--recreate` while any container remains attached.

Inspect the selected non-secret network contract at any time:

```bash
docker network inspect sample-observer |
jq '.[0] | {
  subnet: .IPAM.Config[0].Subnet,
  ip_range: .IPAM.Config[0].IPRange,
  gateway: .IPAM.Config[0].Gateway,
  observer_ip: .Labels["com.nabla.observer-ip"]
}'
```

### Reconcile the TrueNAS source allowlist

Do not retain either historical observer address:

```text
172.16.55.9/32   shared intranet pool; observed owned by Langflow
172.16.56.9/32   failed candidate; its subnet overlaps another address space
```

Use the repository helper. Its default mode is read-only:

```bash
sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh --check
```

It preserves unrelated allowlist entries, removes only the obsolete Sample
observer /32 values above, and derives the desired replacement from the
`sample-observer` network label.

Apply explicitly:

```bash
sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh --apply
```

Re-read the persisted value:

```bash
midclt call system.general.config |
jq '.ui_allowlist'
```

Remove a failed Sample container from previous network attempts. Do **not**
delete or recreate the shared `intranet` network:

```bash
docker rm -f fastapi-sample 2>/dev/null || true
```

Reconcile the TrueNAS Custom App and redeploy:

```bash
sudo midclt call -j app.update sample \
'{
  "custom_compose_config": {
    "include": [
      "/mnt/cpool/compose/nabla-compose/apps/sample/compose.yml"
    ]
  }
}'

sudo midclt call -j app.redeploy sample
```

After the container is running, prove that Docker assigned the network-reserved
address and that TrueNAS accepts the source:

```bash
docker inspect fastapi-sample |
jq '.[0].NetworkSettings.Networks["sample-observer"] | {
  ip: .IPAddress,
  gateway: .Gateway
}'

bash scripts/security/verify-truenas-observer-access.sh
```

Then prove the replacement container, health endpoint and effective version:

```bash
docker inspect fastapi-sample |
jq '.[0] | {
  image: .Config.Image,
  image_id: .Image,
  status: .State.Status,
  health: (.State.Health.Status // "none")
}'

curl -fsS --retry 15 --retry-delay 2 --retry-connrefused \
  http://127.0.0.1:8091/health |
jq .

curl -fsS --retry 5 --retry-delay 1 \
  http://127.0.0.1:8091/v2/version |
jq .
```

If `app.query` does not contain the expected `sample` application, stop
before running `app.update` and inspect the actual application id:

```bash
midclt call app.query |
jq -r '.[] | [.id, .state] | @tsv' |
grep -E '(^|[[:space:]])(sample|fastapi)'
```

Do not run a second `docker compose up` project alongside the TrueNAS Custom
App. Build the image from the repository, then let TrueNAS own the container
lifecycle.

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
WebSocket source addresses **before API-key authentication**. A successful
`GET /api/versions` therefore proves HTTPS reachability only; it does not prove
that `/api/current` is permitted.

For the Docker-hosted observer, TrueNAS sees the FastAPI container address from
the dedicated `sample-observer` bridge, not the TrueNAS LAN address and not
the dynamically allocated shared-`intranet` address. A policy close such as:

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
allow dedicated observer IP /32                  -> system.version + app.query = 86
system.general.checkin                           -> change persisted
```

Run the read-only preflight after every recreate/network change:

```bash
scripts/security/verify-truenas-observer-access.sh
```

Do not allow an entire Docker subnet merely to make this observer work. The
Compose service pins the observer source to
`${FASTAPI_SAMPLE_OBSERVER_IP:-172.16.56.9}` on the dedicated
`sample-observer` bridge (`172.16.56.0/28` by default), matching one reviewed
TrueNAS `/32` allowlist entry. The historical `172.16.55.9/32` entry is
forbidden because that address belongs to the shared `intranet` allocation
pool and can be reassigned to unrelated containers.

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
 \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

docker inspect fastapi-sample 2>/dev/null |
jq '.[0] | {
  status: .State.Status,
  error: .State.Error,
  networks: .NetworkSettings.Networks
}'
```

The host-side port is `8091`; container port `8080` is internal to the
mapping. A listener on host `:8080` does **not** conflict with
`8091:8080`.

When no container owns `172.16.55.9` on any Docker network and
`fastapi-sample` is only a failed `created/exited` container, recover the
stale endpoint without recreating `intranet`:

```bash
docker network disconnect -f intranet fastapi-sample 2>/dev/null || true
docker rm -f fastapi-sample 2>/dev/null || true

sudo midclt call -j app.redeploy sample
```

Do not delete/recreate the shared `intranet` network to clear one stale
endpoint: many independent applications depend on that network and its fixed
subnet.

Build the pinned source before asking TrueNAS to redeploy the Custom App:

```bash
docker compose -f apps/sample/compose.yml \
  build --pull fastapi-sample

sudo midclt call -j app.update sample \
'{
  "custom_compose_config": {
    "include": [
      "/mnt/cpool/compose/nabla-compose/apps/sample/compose.yml"
    ]
  }
}'

sudo midclt call -j app.redeploy sample
```

Then prove the replacement container, health endpoint and effective version:

```bash
docker inspect fastapi-sample |
jq '.[0] | {
  image: .Config.Image,
  image_id: .Image,
  status: .State.Status,
  health: (.State.Health.Status // "none")
}'

curl -fsS --retry 15 --retry-delay 2 --retry-connrefused \
  http://127.0.0.1:8091/health |
jq .

curl -fsS --retry 5 --retry-delay 1 \
  http://127.0.0.1:8091/v2/version |
jq .
```

If `app.query` does not contain the expected `sample` application, stop
before running `app.update` and inspect the actual application id:

```bash
midclt call app.query |
jq -r '.[] | [.id, .state] | @tsv' |
grep -E '(^|[[:space:]])(sample|fastapi)'
```

Do not run a second `docker compose up` project alongside the TrueNAS Custom
App. Build the image from the repository, then let TrueNAS own the container
lifecycle.

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
WebSocket source addresses **before API-key authentication**. A successful
`GET /api/versions` therefore proves HTTPS reachability only; it does not prove
that `/api/current` is permitted.

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
