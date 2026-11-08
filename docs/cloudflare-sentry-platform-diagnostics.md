# Cloudflare / Sentry platform diagnostics

**Canonical owner: `nabla-compose`.** This runbook covers the homelab
Cloudflare Tunnel/Access control plane, public routes and the self-hosted
Sentry ingestion path. The FastAPI-specific observer and SDK fallback contracts
remain in
[fastapi-sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/cloudflare-sentry-runtime-diagnostics.md).
Historical incidents belong in `docs/incidents/`; do not turn a dated
observation into a permanent expected value.

## Cloudflare Tunnel and Access evidence

- Read-only API inventory: Tunnels, connector status, `config_src`, Public
  Hostname routes, Access Applications, reusable policies and assignments,
  Service Tokens and edge connector metadata (colo, version, start time and
  public IP where available). Never print API tokens, Access secrets or DSNs.
- For dashboard-managed Tunnels (`config_src=cloudflare`), the Cloudflare
  API is authoritative for the configured Public Hostname origin. Compare
  host/port with `catalog/service-topology.json` (`internalHost` and
  `internalPort`), **generated** from the canonical service definitions.
  A mismatch is exposure/configuration drift, not proof that the origin
  workload is down.
- `config_src=local` can make provider-side ingress inventory incomplete:
  report **unknown/unverified**, not a fabricated mismatch.
- An API timeout, missing permission or empty inventory is a provider
  observability warning. It must not change a healthy workload to DOWN.
- Tunnel inventory proves route configuration; an authenticated
  **live Service Token request** is stronger evidence of the actual Access
  identity path. Correlate policy and origin health before declaring success.
- For HTTPS probes require TLS 1.2 or newer and certificate verification
  except a separately documented internal transport-only comparison.

Previously observed example (**not** an immutable desired-state contract):

```text
Tunnel: nabla-truescale
2fauth.albandrieu.com -> http://172.17.0.24:30081
```

Compare against current authoritative topology and actual Tunnel API state
on each diagnosis. Distinguish DNS, TCP, TLS, Tunnel, pfSense HAProxy, Traefik,
Access authorization and application response. A WebSocket timeout such as
`Connection timed out - goodbye` proves only a failed transport operation.

Read-only starting points:

```bash
python3 scripts/ingress/audit-internal-routes.py --strict
bash scripts/truenas/audit-app-lifecycle.sh
```

Check each script's runtime dependencies and command-line options before
execution; these commands do not themselves prove a live Access token path.
Avoid probing public services repeatedly during incident recovery.

## Cloudflare observer contract

The observer is read-only: it reconciles Cloudflare API state with the
declared topology and never mutates Cloudflare configuration. The shared
Tunnel Public Hostnames, the DNS records and the protected Access
Applications are declared in [`terraform/cloudflare`](../terraform/cloudflare/README.md)
(OpenTofu, import-first); reusable Access policies stay in the dashboard and
are referenced by ID. Once a resource is adopted there, do not edit it in the
dashboard: the next apply overwrites the drift.

### Dashboard surfaces and API mapping

Dashboard surfaces for the current account (the account ID is not a secret;
API tokens and Service Token secrets must never be logged or committed):

- **Tunnel Public Hostnames**:
  <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/networks/connectors/cloudflare-tunnels/cloudflared/1d98bede-6fa0-42a8-971c-cd390d74d7f6/edit/public-hostname>
- **Access Applications**:
  <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/apps>
- **Access reusable Policies**:
  <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/policies>
- **Access Service Tokens**:
  <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/service-credentials/service-tokens>

A Tunnel **ingress rule** is the API representation of a dashboard Public
Hostname: which origin `cloudflared` contacts for a hostname. In operator
docs say **Tunnel Public Hostname** and keep `config.ingress[]` for the API
field. The hostname-to-origin mapping is **not** an Access policy: Access
decides whether a request is authorized, the Public Hostname decides where an
authorized request is routed.

For a dashboard/API-managed Tunnel (`config_src=cloudflare`) the routes are
read through:

```text
GET /accounts/{account_id}/cfd_tunnel
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
  -> result.config.ingress[]  (hostname, service, originRequest)
```

A local `cloudflared` YAML file is authoritative only for a locally-managed
Tunnel (`config_src=local`); it is not required to observe this Tunnel.

Access objects:

```text
GET /accounts/{account_id}/access/apps
GET /accounts/{account_id}/access/apps/{app_id}/policies
GET /accounts/{account_id}/access/policies
GET /accounts/{account_id}/access/service_tokens
```

- **Application**: protected hostname/path and settings.
- **Application policies**: policies actually attached, reusable ones included.
- **Reusable policies**: account-level objects available for assignment.
- **Service Tokens**: machine credentials selected by a `Service Auth` policy.

A machine-to-machine policy uses action **Service Auth** with an Include rule
selecting the intended Service Token. A token present in the account does not
prove it is assigned to the application.

### Read permissions and resource scope

The observer API token is account-scoped (**Include → Specific account →
bdfe00eeee5845782ab91adfbff71ee1**) with **Cloudflare Tunnel Read** (or
**Cloudflare One Connector: cloudflared Read**), **Access: Apps and Policies
Read** and, for Service Token correlation, **Access: Service Tokens Read**.

Token validity and resource authorization are separate. A user-owned token can
be active on `/user/tokens/verify` while `/accounts/{account_id}/tokens/verify`
returns `401`; that does not invalidate it. List endpoints are
authorization-aware: **HTTP 200 with an empty Tunnel list is not proof that
the account has no Tunnels**, and a direct lookup of a known Tunnel returning
`401 Not authorized` proves missing permission/scope for that token. The same
rule applies to Access inventory: an empty list is never a positive claim that
no Application, Policy or Service Token exists when edge evidence says
otherwise.

### Diagnostic

Run from the workstation, TrueNAS, then the FastAPI container:

```bash
python3 scripts/cloudflare/diagnose-cloudflare-api.py \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname 2fauth.albandrieu.com \
  --access-url https://2fauth.albandrieu.com/
```

- The direct Tunnel lookup distinguishes an empty inventory from an
  authorization-filtered list (`result_count=0`).
- The Access edge probe does not follow redirects: following a challenge to
  the login page would turn it into a final 200 and a false
  `access_blocked=false`. Strong Service Auth proof is anonymous request
  blocked/challenged **and** Service Token request allowed; two unblocked 200s
  prove nothing, so inspect the application/policy inventory.
- On TrueNAS without `mise`, export the variables first (`set -a`, source
  `.env.local` / `.env.secrets` if present, `set +a`) and never print the
  environment afterwards.
- The FastAPI container is a separate context with its own credentials; test
  exactly what it sees with
  `docker exec -i fastapi-sample python - <same arguments> < scripts/cloudflare/diagnose-cloudflare-api.py`.

### Layered evidence for health verdicts

1. public DNS / HTTP / TLS;
2. Cloudflare edge headers;
3. Tunnel object and `config_src`;
4. Tunnel Public Hostname (`config.ingress[]`) hostname-to-origin mapping;
5. Access application;
6. policies attached to the application;
7. Service Token inventory and Service Auth selection;
8. live anonymous-vs-Service-Token edge probe.

A failure, timeout, authorization filtering or empty control-plane inventory
is a **warning/unknown** state, never enough to mark an application DOWN or a
Tunnel/Application absent. Conversely, an HTTP 200 alone does not prove the
declared Access protection.

## Self-hosted Sentry: transport vs ingestion

The self-hosted Sentry intake is reached through the declared LAN endpoint
`http://172.17.0.24:9005` for the homelab deployment; validate the
**running** port and container state rather than assuming a Compose file is
deployed. Keep Cloudflare Access and Sentry User Auth as distinct security
boundaries when checking the protected public UI/API path.

Prove each layer separately:

1. Container/relay and downstream dependencies (Kafka, Snuba, ClickHouse,
   Redis and PostgreSQL) using their appropriate targeted health evidence.
2. DSN TCP or HTTP/TLS reachability — **transport only**, no event ingestion
   guarantee. Never reuse a SaaS DSN public key for the self-hosted project.
3. A controlled **synthetic event ID**, confirmed through downstream
   project/event lookup or the existing `scripts/truenas/smoke-sentry-event.sh`
   acceptance procedure; a 2xx/202 intake response alone is insufficient.
4. Route-specific Access Service Token authentication and Sentry User Auth
   separately; a 302 login redirect is not Sentry ingestion success.

Before running a synthetic-event smoke, review its arguments and ensure it
targets a non-sensitive test project; never print DSNs, tokens, event payloads
or user data. Retain correlation identifiers and bounded latency/status
evidence, not full private request bodies or document contents.

## Ownership and no false positives

| Concern | Owner |
| --- | --- |
| Cloudflare/Tunnel/Access configuration, route topology, Sentry self-hosted operations and recovery | `nabla-compose` |
| Health-board Cloudflare badges, cache/fan-out, topology-origin drift verdict and provider uncertainty | `fastapi-sample` |
| FastAPI `SENTRY_LOCAL_DSN` / `SENTRY_DSN` fallback, SDK sampling, sanitized startup logs and WebSocket tagging | `fastapi-sample` |

Do not equate a Cloudflare provider API timeout with an origin outage, or a
Sentry socket probe with a persisted event. A local Sentry outage stays visible
to the homelab observer even if an application falls back to SaaS telemetry.
