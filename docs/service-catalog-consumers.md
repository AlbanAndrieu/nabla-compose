# Service catalog consumers: Homarr, Heimdall, Gatus and Uptime Kuma

The Nabla `x-nabla` metadata and generated `catalog/services.json` remain the source of truth for service identity, presentation and architecture. Dashboard or monitoring products are consumers of that catalog; they must not become competing service inventories.

```text
apps/**/compose.yml x-nabla
          |
          v
catalog/services.json + service-topology.json
          |
          +--> Homarr apps / boards
          +--> Heimdall item REST/import format
          +--> Gatus endpoint YAML
          +--> AutoKuma monitor definitions --> Uptime Kuma
```

## Current catalog capabilities

A declared service can already provide a stable `id`, display `name`, `kind`, `category`, optional `url`, optional `description`, icon, runtime/provider binding and architecture relations. This is enough for dashboard/bookmark generation, but not for reliable health monitoring: a dashboard URL is not necessarily a health endpoint.

## Consumer comparison

| Consumer | Config/API surface | MCP | Recommended Nabla integration |
| --- | --- | --- | --- |
| Homarr | OpenAPI + tRPC, API-key auth; Docker app discovery | Native MCP, 50+ tools | Reconcile catalog apps through API/MCP; Docker discovery only as enrichment |
| Heimdall | `GET api/item` / `POST api/item` item round-trip | No credible LinuxServer-Heimdall-specific MCP found | Generate item payloads; never mutate SQLite directly |
| Gatus | Native YAML; self-hosted status APIs | Community `adambenhassen/gatus-mcp` | Generate YAML from explicit monitoring metadata |
| Uptime Kuma | Internal Socket.IO management protocol | Community `@davidfuchs/mcp-uptime-kuma` for v2 | Generate AutoKuma definitions; reserve MCP for operator interactions |

## Homarr

Homarr app fields map naturally to the Nabla catalog: name, URL, description and icon. Homarr also supports a distinct ping URL.

Homarr exposes authenticated OpenAPI/tRPC APIs. API keys are passed using the `ApiKey` header. The stable Homarr MCP endpoint is currently `/api/mcp/mcp`; Homarr v2 prefers `/api/mcp` and keeps the previous URL as a compatibility alias. For that reason the repository expects the complete URL in `HOMARR_MCP_URL`.

| Nabla | Homarr |
| --- | --- |
| `id` | stable synchronization identifier/tag |
| `name` | app name |
| `url` | app URL |
| `description` | description |
| `icon` | icon/presentation mapping |
| future `monitoring.target` | ping URL |
| `category` | board/section/tag policy |

Docker discovery cannot represent external/logical catalog nodes such as pfSense, so it should not replace `x-nabla`.

```bash
export HOMARR_MCP_URL='https://homarr.example.internal/api/mcp/mcp'
export HOMARR_API_KEY='...'
```

For Homarr v2 prefer `/api/mcp`.

## Heimdall

LinuxServer Heimdall 2.8.x has a concrete item round-trip through `ItemRestController`. Export uses `GET api/item`; import posts payloads to `api/item`.

The current exported shape is:

```json
{
  "title": "Grafana",
  "colour": "#f46800",
  "url": "https://grafana.example.internal",
  "description": "Observability dashboard",
  "appid": "...",
  "appdescription": "...",
  "tags": ["Observability"]
}
```

The exported keys are exactly `title`, `colour`, `url`, `description`, `appid`, `appdescription` and `tags`. Tags are exported by title, excluding the root/default dashboard tag. On import an existing tag with the same title is reused and a missing one is created; empty/omitted tags fall back to the root dashboard.

| Nabla | Heimdall |
| --- | --- |
| `name` | `title` |
| `url` | `url` |
| `description` | `description` |
| `category` | one entry in `tags` |
| Heimdall app match | `appid` / `appdescription` |

`colour`, `appid` and `appdescription` need consumer-specific defaults/matching and should not pollute the generic `x-nabla` model. Keep reconciliation conservative and do not modify `/config/www/app.sqlite` directly.

No MCP entry is added for Heimdall. Search results named "Heimdall MCP" refer to unrelated products, not the LinuxServer application dashboard.

## Gatus

Gatus is the strongest declarative monitoring target. Self-hosted Gatus consumes YAML; if `GATUS_CONFIG_PATH` points to a directory, YAML files below it are merged.

```yaml
endpoints:
  - name: FastAPI Sample
    group: api
    url: https://fastapi-sample.fastapicloud.dev/health
    interval: 30s
    conditions:
      - "[STATUS] == 200"
```

Gatus supports HTTP, TCP, ICMP, DNS, TLS and external/push checks, so generation must consume explicit monitoring metadata rather than guessing from `url`.

The generated Gatus configuration enables its Prometheus-compatible `/metrics`
endpoint. This provides synthetic service evidence such as endpoint success,
request duration, HTTP result codes and certificate lifetime. Treat these as
black-box probe signals: they describe the monitored path from Gatus, not real
application request traffic or proof of security-control effectiveness.

Do not duplicate this function with another black-box probe stack by default.
The follow-up Prometheus integration should scrape Gatus and derive bounded
recording rules for service availability/latency while preserving a stable Nabla
service identity.

The selected community MCP is `adambenhassen/gatus-mcp`. It serves Streamable HTTP on `/mcp`. Status/history tools are read-only; `submit_external_result` is the write operation and requires a Gatus token.

```bash
export GATUS_MCP_URL='http://gatus-mcp:3000/mcp'
```

Do not provide `GATUS_TOKEN` to that MCP deployment unless external-result submission is intentionally required.

## Uptime Kuma

Uptime Kuma 2.x performs management through its internal Socket.IO protocol. That protocol should not become the Nabla synchronization contract.

Use AutoKuma as the declarative adapter. AutoKuma supports Docker labels and JSON/TOML file sources. Label keys have the form:

```text
kuma.<id>.<type>.<setting>
```

Example:

```yaml
labels:
  kuma.fastapi.http.name: FastAPI Sample
  kuma.fastapi.http.url: https://fastapi-sample.fastapicloud.dev/health
```

Generated AutoKuma files are preferable to manually placing monitoring labels in every Compose service because `x-nabla` stays authoritative and consumer policy stays centralized.

The MCP `@davidfuchs/mcp-uptime-kuma` is pinned to `0.11.9`. It targets Uptime Kuma v2 and supports monitor, heartbeat, notification, tag, maintenance and status-page operations. It is write-capable, including deletion. `UPTIME_KUMA_INCLUDE_SECRETS=false` is forced in project MCP configuration so read operations redact credentials by default.

```bash
export UPTIME_KUMA_URL='https://uptime.example.internal'
export UPTIME_KUMA_USERNAME='...'
export UPTIME_KUMA_PASSWORD='...'
```

The stdio package requires Node.js 22 or later. For 2FA accounts it also supports `UPTIME_KUMA_JWT_TOKEN`, which takes precedence over username/password. Never enable `UPTIME_KUMA_INCLUDE_SECRETS=true` globally for an AI client.

## TrueNAS 26

`truenas/api_client` remains the native Python/`midclt` client. It supports the current `/api/current` JSON-RPC 2.0 stack and TrueNAS 26 SCRAM-SHA-512 API-key authentication. It is not itself an MCP server.

The official `truenas/truenas-mcp` research-preview implementation is not selected for this TrueNAS 26 configuration. Its current source still:

- connects to `wss://<host>:443/websocket`;
- sends the legacy DDP-style `msg: connect` handshake;
- authenticates using `auth.login_with_api_key`.

That transport is not the right basis for a TrueNAS 25.10+/26 MCP integration.

The repository therefore uses the third-party read-only `@profanter-dev/truenas-mcp`, pinned to `1.0.6`. It targets TrueNAS SCALE 25.10+, uses `wss://<host>/api/current` JSON-RPC 2.0, and exposes no mutating tools.

```bash
export TRUENAS_MCP_HOST='truenas.example.internal:443'
export TRUENAS_MCP_API_KEY='...read-only API key...'
export TRUENAS_MCP_INSECURE=false
```

`TRUENAS_MCP_HOST` is `host[:port]`, without an `https://` prefix. Keep TLS verification enabled when possible. The selected MCP still authenticates with `auth.login_with_api_key`, which is deprecated in TrueNAS 26; before TrueNAS 27, reassess it or move to an MCP/wrapper using the modern `truenas/api_client`/SCRAM path.

Do not reuse the OpenTofu/Terragrunt write credential for MCP inspection.

## FastAPI Sample

`AlbanAndrieu/fastapi-sample` exposes FastMCP Streamable HTTP on `/mcp` from the same FastAPI process. Its local project configuration uses `http://127.0.0.1:8080/mcp`.

The Nabla root MCP config defaults to:

```text
https://fastapi-sample.fastapicloud.dev/mcp
```

It can be overridden in clients that support default environment expansion:

```bash
export FASTAPI_SAMPLE_MCP_URL='http://127.0.0.1:8080/mcp'
```

Cursor points directly to the production URL.

## Proposed monitoring metadata

Do not infer health semantics from `url`. Add optional, validated service-local monitoring metadata before generating Gatus or AutoKuma resources:

```yaml
x-nabla:
  id: example
  name: Example
  kind: application
  category: application
  url: https://example.internal
  monitoring:
    enabled: true
    type: http
    target: https://example.internal/health
    interval: 30s
    group: application
    conditions:
      - "[STATUS] == 200"
```

Suggested initial fields:

- `enabled`: explicit opt-in;
- `type`: `http`, `tcp`, `icmp`, `dns`, `tls`, `grpc` or `external`;
- `target`: health target distinct from the dashboard URL;
- `interval`: probe interval;
- `group`: monitoring group;
- `conditions`: assertions where applicable;
- consumer overrides only where a target cannot be represented portably.

## Intended generated artifacts

Once monitoring metadata exists, generate deterministic consumer files, for example:

```text
generated/consumers/homarr.json
generated/consumers/heimdall.json
generated/consumers/gatus.yaml
generated/consumers/autokuma.toml
```

Rules:

1. generated consumer files are never a source of truth;
2. no passwords, API keys, cookies or bearer tokens are emitted;
3. stable `x-nabla.id` values are reconciliation identifiers;
4. consumer deletion requires an explicit policy rather than blind destructive sync;
5. generation must be deterministic and enforced by the quality gate.

## MCP environment inventory

| Variable | Purpose |
| --- | --- |
| `TRUENAS_MCP_HOST` | TrueNAS 25.10+/26 JSON-RPC host and optional port |
| `TRUENAS_MCP_API_KEY` | dedicated read-only TrueNAS API key |
| `TRUENAS_MCP_INSECURE` | optional self-signed TLS bypass; prefer `false` |
| `HOMARR_MCP_URL` | full Homarr MCP URL |
| `HOMARR_API_KEY` | Homarr API key sent in `ApiKey` header |
| `GATUS_MCP_URL` | separately deployed Gatus MCP URL |
| `UPTIME_KUMA_URL` | Uptime Kuma v2 base URL |
| `UPTIME_KUMA_USERNAME` | Uptime Kuma user |
| `UPTIME_KUMA_PASSWORD` | Uptime Kuma password |
| `FASTAPI_SAMPLE_MCP_URL` | optional root-config FastAPI Sample override |

## Upstream references

- Homarr API: https://homarr.dev/docs/management/api/
- Homarr MCP: https://homarr.dev/docs/management/mcp/
- Heimdall item round-trip: https://github.com/linuxserver/Heimdall/pull/1567
- Gatus: https://gatus.io/docs/endpoints
- Gatus MCP: https://github.com/adambenhassen/gatus-mcp
- AutoKuma: https://github.com/BigBoot/AutoKuma
- Uptime Kuma MCP: https://github.com/DavidFuchs/mcp-uptime-kuma
- TrueNAS API client: https://github.com/truenas/api_client
- Official TrueNAS MCP research preview: https://github.com/truenas/truenas-mcp
- TrueNAS 25.10+/26 read-only MCP: https://github.com/profanter-dev/truenas-mcp
