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
