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

A declared service can already provide:

- stable `id`;
- display `name`;
- `kind` and `category`;
- optional `url`;
- optional `description`;
- presentation `icon` through the icon catalog;
- runtime/provider binding;
- architecture relations in the topology contract.

This is already sufficient to generate dashboard/bookmark entries. It is not sufficient to generate reliable health monitors because a dashboard URL is not necessarily a health endpoint.

## Consumer comparison

| Consumer | Native declarative/config surface | Programmatic API | MCP | Recommended Nabla integration |
| --- | --- | --- | --- | --- |
| Homarr | Apps are stored by Homarr; Docker discovery can create apps | OpenAPI + tRPC with API-key auth | Native MCP, 50+ tools | Sync catalog apps through Homarr API/MCP; use Docker discovery only as enrichment |
| Heimdall | Item import/export through the UI | `GET api/item` / `POST api/item` item REST path exists, but no general supported automation API | No credible LinuxServer-Heimdall-specific MCP found | Generate the documented item payload; never mutate Heimdall SQLite directly |
| Gatus | Native YAML endpoint configuration | Self-hosted status APIs; Gatus.io also exposes an external API | Community `adambenhassen/gatus-mcp` | Generate a dedicated YAML fragment from explicit monitoring metadata |
| Uptime Kuma | UI/database driven | Internal Socket.IO API; not a stable public CRUD contract | Community `@davidfuchs/mcp-uptime-kuma` for v2 | Generate AutoKuma file/label definitions; use MCP for operator interactions, not as source of truth |

## Homarr

Homarr applications have the same basic fields already present in the Nabla catalog: name, URL, description and icon. Homarr can also use a separate ping URL.

Homarr exposes an authenticated API suitable for automation. API keys use the `ApiKey` HTTP header. The stable Homarr MCP endpoint is currently `/api/mcp/mcp`; Homarr v2 uses `/api/mcp` and keeps the older path as a compatibility alias. For that reason this repository does not hard-code the Homarr MCP path and expects `HOMARR_MCP_URL`.

Recommended mapping:

| Nabla | Homarr |
| --- | --- |
| `id` | stable external synchronization key/tag |
| `name` | app name |
| `url` | app URL |
| `description` | app description |
| `icon` | app icon/presentation mapping |
| future `monitoring.target` | ping URL |
| `category` | board/section/tag policy |

Docker discovery remains useful for container metadata but cannot represent external/logical services such as pfSense or other non-container dependencies, so it should not replace the Nabla catalog.

MCP configuration requires:

```bash
export HOMARR_MCP_URL='https://homarr.example.internal/api/mcp/mcp'
export HOMARR_API_KEY='...'
```

For Homarr v2 prefer `/api/mcp`.

## Heimdall

LinuxServer Heimdall 2.8.x has a concrete item round-trip through `ItemRestController`. The export path is `GET api/item`; the import path posts item payloads to `api/item`.

The current exported item structure is:

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

The exported keys are exactly `title`, `colour`, `url`, `description`, `appid`, `appdescription` and `tags`. Tags are exported by title, excluding the root/default dashboard tag. On import, an existing tag with the same title is reused and a missing tag is created, so tag reconciliation is idempotent by title. Empty/omitted tags fall back to the root dashboard.

Recommended initial mapping:

| Nabla | Heimdall |
| --- | --- |
| `name` | `title` |
| `url` | `url` |
| `description` | `description` |
| `category` | one entry in `tags` |
| icon/app catalog match | `appid` / `appdescription` where a matching Heimdall app exists |

`colour`, `appid` and `appdescription` need a Heimdall-specific mapping/default policy; they should not be invented in `x-nabla` merely for one consumer.

Although this item REST path makes deterministic import possible, Heimdall still does not expose a broad supported dynamic application-management API comparable to Homarr. Keep synchronization conservative and do not directly manipulate `/config/www/app.sqlite`.

No MCP entry is added for Heimdall. Projects named "Heimdall MCP" found during research refer to unrelated security/AI products rather than the LinuxServer application dashboard.

## Gatus

Gatus is the strongest declarative target. Self-hosted Gatus consumes YAML and can merge all `.yaml`/`.yml` files below a directory when `GATUS_CONFIG_PATH` points to that directory.

A typical generated endpoint is structurally equivalent to:

```yaml
endpoints:
  - name: FastAPI Sample
    group: api
    url: https://fastapi-sample.fastapicloud.dev/health
    interval: 30s
    conditions:
      - "[STATUS] == 200"
```

Gatus supports endpoint types beyond HTTP, including TCP, ICMP, DNS, TLS and external/push monitoring. The generator therefore must consume explicit monitoring metadata instead of guessing from a service URL.

The selected community MCP is `adambenhassen/gatus-mcp`. It wraps the Gatus REST API and serves Streamable HTTP at `/mcp`. Its normal status/history tools are read-only; `submit_external_result` is the only write operation and requires a Gatus token.

This repository expects the MCP to be deployed separately and configured with:

```bash
export GATUS_MCP_URL='http://gatus-mcp:3000/mcp'
```

Do not provide `GATUS_TOKEN` to the MCP deployment unless external-result submission is intentionally required.

## Uptime Kuma

Uptime Kuma 2.x primarily exposes its management operations through its internal Socket.IO protocol. That interface is not a stable public CRUD API and should not become the Nabla synchronization contract.

Use AutoKuma as the declarative adapter. AutoKuma can derive monitors from Docker labels or JSON/TOML files. Its Docker label structure is:

```text
kuma.<id>.<type>.<setting>
```

For example:

```yaml
labels:
  kuma.fastapi.http.name: FastAPI Sample
  kuma.fastapi.http.url: https://fastapi-sample.fastapicloud.dev/health
```

For this repository, generated AutoKuma file definitions are preferable to manually adding labels to every application Compose file because they keep monitoring policy in one generated consumer artifact while `x-nabla` remains authoritative.

The selected MCP is `@davidfuchs/mcp-uptime-kuma`, pinned to `0.11.9` in the project configs. It targets Uptime Kuma v2 and supports monitor, heartbeat, notification, tag, maintenance and status-page operations. It is write-capable, including monitor deletion. The repository forces `UPTIME_KUMA_INCLUDE_SECRETS=false` so read operations keep credentials redacted by default.

Required environment variables:

```bash
export UPTIME_KUMA_URL='https://uptime.example.internal'
export UPTIME_KUMA_USERNAME='...'
export UPTIME_KUMA_PASSWORD='...'
```

For accounts using 2FA, the MCP also supports `UPTIME_KUMA_JWT_TOKEN`; prefer that mode when operationally convenient. Never enable `UPTIME_KUMA_INCLUDE_SECRETS=true` globally for an AI client.

## TrueNAS

`truenas/api_client` is a Python/JSON-RPC client and provides tools such as `midclt`; it is not an MCP server.

Use the official `truenas/truenas-mcp` server instead. The existing `truenas-readonly` configuration is deliberately backed by a dedicated TrueNAS read-only API key/RBAC identity:

```bash
export TRUENAS_URL='https://truenas.example.internal'
export TRUENAS_MCP_API_KEY='...read-only API key...'
```

Do not reuse the OpenTofu/Terragrunt write credential for MCP inspection.

## FastAPI Sample

`AlbanAndrieu/fastapi-sample` exposes FastMCP Streamable HTTP on `/mcp` from the same FastAPI process. The local repository configuration uses `http://127.0.0.1:8080/mcp`.

The Nabla project-level MCP configuration defaults to:

```text
https://fastapi-sample.fastapicloud.dev/mcp
```

Claude-compatible project configuration can override it with:

```bash
export FASTAPI_SAMPLE_MCP_URL='http://127.0.0.1:8080/mcp'
```

Cursor currently uses the production URL directly because its project environment interpolation syntax does not provide the same portable default-value expression.

## Proposed monitoring metadata

Do not infer health semantics from `url`. Extend service-local `x-nabla` with optional monitoring metadata before generating Gatus or AutoKuma resources:

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
- `conditions`: Gatus-compatible assertions where applicable;
- optional consumer overrides only when a target cannot be represented portably.

The schema/generator should validate this block before any consumer exporter is introduced.

## Intended generated artifacts

Once monitoring metadata exists, add a deterministic generator, for example:

```text
generated/consumers/homarr.json
generated/consumers/heimdall.json
generated/consumers/gatus.yaml
generated/consumers/autokuma.toml
```

The exact paths may change, but these rules should not:

1. generated consumer files are never a source of truth;
2. no passwords, API keys, cookies or bearer tokens are written to generated files;
3. stable `x-nabla.id` values are used as reconciliation identifiers;
4. removing a service from a consumer requires an explicit reconciliation policy rather than blind destructive deletion;
5. generation is deterministic and enforced by the repository quality gate.

## MCP environment inventory

The root `.mcp.json` and `.cursor/mcp.json` require or use:

| Variable | Purpose |
| --- | --- |
| `TRUENAS_URL` | TrueNAS middleware endpoint |
| `TRUENAS_MCP_API_KEY` | dedicated read-only TrueNAS API key |
| `HOMARR_MCP_URL` | complete Homarr MCP URL, including version-appropriate path |
| `HOMARR_API_KEY` | Homarr API key sent in `ApiKey` header |
| `GATUS_MCP_URL` | separately deployed `gatus-mcp` Streamable HTTP URL |
| `UPTIME_KUMA_URL` | Uptime Kuma v2 base URL |
| `UPTIME_KUMA_USERNAME` | Uptime Kuma user for stdio MCP |
| `UPTIME_KUMA_PASSWORD` | Uptime Kuma password for stdio MCP |
| `FASTAPI_SAMPLE_MCP_URL` | optional root-config override for FastAPI Sample MCP |

## Upstream references

- Homarr API: https://homarr.dev/docs/management/api/
- Homarr MCP: https://homarr.dev/docs/management/mcp/
- Heimdall item round-trip: https://github.com/linuxserver/Heimdall/pull/1567
- Gatus endpoints: https://gatus.io/docs/endpoints
- Gatus repository/configuration: https://github.com/TwiN/gatus
- Gatus MCP: https://github.com/adambenhassen/gatus-mcp
- AutoKuma: https://github.com/BigBoot/AutoKuma
- Uptime Kuma MCP: https://github.com/DavidFuchs/mcp-uptime-kuma
- Heimdall: https://github.com/linuxserver/Heimdall
- TrueNAS API client: https://github.com/truenas/api_client
- TrueNAS MCP: https://github.com/truenas/truenas-mcp
