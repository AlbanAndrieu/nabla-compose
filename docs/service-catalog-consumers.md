# Service catalog consumers: Homarr, Heimdall, Gatus and Uptime Kuma

The **v2 source of truth is native Backstage** (`catalog-info.yaml`) for entity
identity, title, owner, tags, links, and standard relations. Docker Compose owns
runtime bindings. **Gatus native YAML** owns monitoring targets and conditions.
Consumer files are generated read models, never independent inventories.

```text
catalog/catalog-info.yaml + apps/*/catalog-info.yaml
                       + Docker Compose labels/ports/Traefik routing
                              |
                              v
                 generate-service-consumers.py
                              |
                              +--> Homarr generated/apps.json
                              |
config/monitoring/gatus-endpoints.yml (Gatus native endpoints)
                              |
                              +--> Gatus config/config.yml
                              +--> AutoKuma generated-monitors.json --> Uptime Kuma

Backstage --> catalog/generated/entities.json + homelab.cdx.json (CycloneDX)
```

`catalog/generated/operator-inventory.json` is the native operational graph
projection, associated with the verified Backstage revision and explicit Compose
identity crosswalk. TrueNAS recovery and lifecycle readers use this single export.
The v1 `services.json` and `service-topology.json` are temporary parity/rollback
exports only; remove after FastAPI deployment and before/after plan acceptance.
The consumer generator does not read either old JSON.
All 85 existing Gatus checks are preserved as native probes; the 80 currently
materialized Homarr entries are limited by the still-incomplete Backstage/Compose
identity coverage (143 entries existed under the old generator).

## Current catalog capabilities

Use Backstage `entityRef` as the join key; use `metadata.links` for intentional
UI destinations, rather than treating a dashboard URL as a health endpoint.
Only routing/ports infer presentation links. Gatus probes are explicit, preserve
native `conditions` and can enrich metrics with `nabla_entity_ref`.

## Consumer comparison

| Consumer | Config/API surface | MCP | Recommended Nabla integration |
| --- | --- | --- | --- |
| Homarr | OpenAPI + tRPC, API-key auth; Docker app discovery | Native MCP, 50+ tools | Reconcile catalog apps through API/MCP; Docker discovery only as enrichment |
| Heimdall | `GET api/item` / `POST api/item` item round-trip | No credible LinuxServer-Heimdall-specific MCP found | Generate item payloads; never mutate SQLite directly |
| Gatus | Native YAML; self-hosted status APIs | Community `adambenhassen/gatus-mcp` | Keep native Gatus endpoint YAML as authored and generate its runtime config |
| Uptime Kuma | Internal Socket.IO management protocol | Community `@davidfuchs/mcp-uptime-kuma` for v2 | Generate AutoKuma definitions; reserve MCP for operator interactions |

## Homarr

Homarr app fields map naturally to the Nabla catalog: name, URL, description and icon. Homarr also supports a distinct ping URL.

Homarr exposes authenticated OpenAPI/tRPC APIs. API keys are passed using the `ApiKey` header. The stable Homarr MCP endpoint is currently `/api/mcp/mcp`; Homarr v2 prefers `/api/mcp` and keeps the previous URL as a compatibility alias. Cursor reads the complete URL from `HOMARR_MCP_URL`; `.mcp.json` reaches it through the [LiteLLM MCP gateway](#litellm-mcp-gateway).

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

The TrueNAS App `mcp-gatus` builds it from a pinned commit on digest-pinned
bases (`apps/mcp-gatus/Dockerfile`) and serves `http://172.17.0.24:8015/mcp`;
clients reach it through the [LiteLLM MCP gateway](#litellm-mcp-gateway).

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

Generated AutoKuma files reuse the **same native Gatus probes**; no separate AutoKuma target inventory is maintained. Backstage stays authoritative for entity identity.

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

`.mcp.json` starts `scripts/mcp/truenas-readonly.sh`. The launcher reads the key
from `TRUENAS_MCP_API_KEY` or from `~/.config/nabla/mcp/truenas-readonly.key`, a
file that must be yours with mode 600. It starts the package outside the repository,
because the package loads `dotenv` from its working directory.

TLS stays verified. The TrueNAS certificate names only `truenas.albandrieu.com`, which
resolves to the Cloudflare Tunnel from the LAN. The preload `truenas-pin-host.mjs` pins
that name to `172.17.0.24` for this process only, and `TRUENAS_INSECURE` stays `false`.
`TRUENAS_MCP_HOST` (default `truenas.albandrieu.com:7000`) and `TRUENAS_MCP_ADDR`
(default `172.17.0.24`) override the target.

The key belongs to a dedicated user, `mcp_readonly`, a member of
`truenas_readonly_administrators` (role `READONLY_ADMIN`). Create the user and the key
from the owner terminal, with the TrueNAS ControlMaster open and Vaultwarden unlocked:

```bash
scripts/truenas/mcp-readonly-identity.sh check
scripts/truenas/mcp-readonly-identity.sh apply
```

`apply` writes the key file and the Vaultwarden item `nabla/prod/truenas-mcp-readonly`.
It never prints the key. A missing local copy rotates the key.

The package still authenticates with `auth.login_with_api_key`. This method is
deprecated since TrueNAS 26 (renamed 27). Before TrueNAS 28, reassess it, or move to an
MCP or wrapper on the modern `truenas/api_client`/SCRAM path.

Do not reuse the OpenTofu/Terragrunt write credential for MCP inspection.

## FastAPI Sample

`AlbanAndrieu/fastapi-sample` exposes FastMCP Streamable HTTP on `/mcp` from the same FastAPI process. Its local project configuration uses `http://127.0.0.1:8080/mcp`.

The TrueNAS runtime serves it at `http://172.17.0.24:8091/mcp` behind the internal `X-MCP-Key` credential: without `MCP_OPS_KEY` in Sample's runtime it answers 503 `Operational access unavailable`. `.mcp.json` starts a launcher that sends that header (see [LiteLLM MCP gateway](#litellm-mcp-gateway)).

Cursor points directly to the production URL.

### Site catalog v2 contract

`nabla-compose` publishes `catalog/generated/entities.json` and
`catalog/generated/identity-map.json` with the **same** `catalogRevision`.
The identity map (crosswalk) is **generated** from the Compose
`com.albandrieu.nabla.entity-ref` labels and Gatus identifiers, with
`sourceType`, `sourceId`, `entityRef` and `evidence`; there is no
hand-maintained second mapping. Counts in these artifacts describe Git, not
the TrueNAS runtime.

`fastapi-sample` serves the verified Backstage graph to the site on
`GET /api/site/catalog/v2` (server-side `X-Diagnostics-Key` header):
`schemaVersion=2`, `model=backstage`, `catalogRevision` and redacted
`entities[]`. Site Alban (`lib/homelabSiteCatalog.ts`,
`lib/homelabServicesServer.ts`) reads this endpoint, not
`/api/homelab-services`.

`DIAGNOSTICS_ACCESS_KEY=1234` is a deliberate **negative Vercel fixture**: a
FastAPI 401/403 maps to `access-denied`, with no alternative key attempt, no
secret in the browser, no v1 fallback and no false application DOWN state.
The real key is never written to Git nor requested in a PR. Do not add Vercel
egress IPs to `HOMELAB_TRUSTED_CIDRS`: the SERVICE key and the OWNER
authorization are two separate controls.

Acceptance to maintain:

- JSON projections are reproducible (`--check`);
- correlation IDs are unique and audited with provenance, never inferred from
  a name or IP address alone;
- health logic distinguishes `unknown`/`access-denied`/`probe failed` from a
  confirmed `DOWN`;
- remaining v1 readers (TrueNAS scripts, FastAPI, site) are retired through
  their own migrations.

For multi-layer catalog errors, use the
[cross-cutting diagnostics runbook](runbooks/homelab-e2e-diagnostics.md).

### Synthetic Open Schema outside-in checks

`scripts/generate-synthetic-open-schema.py` generates one SOS v1 YAML
resource per check (`<service>-public-{dns,tls,http}.yaml` under
`generated/synthetic-open-schema/`) for the independent FastAPI
Cloud/outside-in observer, not for the TrueNAS Gatus observer. Public exposure intent now comes from canonical Backstage v2
`catalog/generated/entities.json` (`x-nabla.exposure`), rather than the retired
`catalog/homelab-services.json` synthetic input. Its generated resources carry
`nabla_entity_ref` for correlation. The Backstage snapshot currently declares
33 public HTTPS routes versus 28 in the legacy overlay: five intentionality
mismatches (Immich, n8n, Reactive Resume, Scrutiny, TrueNAS) require provider
reconciliation before deleting historical operational files. A declared public
route is not evidence that its endpoint is reachable.

Cloudflare Access protected HTTP checks only carry environment placeholders
(`CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}`,
`CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}`); no credential value is
copied. SOS does **not** replace the anonymous Cloudflare default-deny probe:
the FastAPI adapter still proves anonymous access is blocked/challenged before
a machine Service Token is tried.

## Legacy monitoring metadata (not part of v2)

Do not infer health semantics from a dashboard `url`. The following `x-nabla.monitoring` shape was a v1 proposal, **not** an authoritative v2 representation; use native `config/monitoring/gatus-endpoints.yml` instead:

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

## Actual generated artifacts

Once monitoring metadata exists, generate deterministic consumer files, for example:

```text
apps/homarr/generated/apps.json
apps/gatus/config/config.yml
apps/autokuma/static/generated-monitors.json
catalog/generated/entities.json
catalog/generated/homelab.cdx.json
```

Rules:

1. generated consumer files are never a source of truth;
2. no passwords, API keys, cookies or bearer tokens are emitted;
3. stable `x-nabla.id` values are reconciliation identifiers;
4. consumer deletion requires an explicit policy rather than blind destructive sync;
5. generation must be deterministic and enforced by the quality gate.

## LiteLLM MCP gateway

Owner decision (22/11/2026): MCP servers sit behind the LiteLLM MCP gateway of
TrueNAS. Clients reach all of them at `http://172.17.0.24:4000/mcp/` with one
virtual key, so Claude Code, Cursor, OpenCode, OpenWebUI, n8n and OpenClaw share
one endpoint, and upstream secrets stay on TrueNAS.

| Server | Declared in | Upstream | Upstream credential | Tool filter |
| --- | --- | --- | --- | --- |
| cyberbro | `apps/litellm/config.yaml` | `mcp-cyberbro` sidecar, 8013 | none | all |
| homarr | LiteLLM database (`mcp-gateway.sh`) | `http://172.17.0.24:30100/api/mcp/mcp` | `nabla/prod/homarr` `HOMARR_API_KEY`, `api_key` auth sent as `ApiKey` (`upstream_token_header`) | 77 tools Homarr annotates `readOnlyHint` (`scripts/litellm/homarr-readonly-tools.json`) |
| grafana | LiteLLM database (`mcp-gateway.sh`) | App `mcp-grafana`, 8014, `-disable-write` | bearer `MCP_GRAFANA_SERVER_TOKEN` (`nabla/prod/grafana-observability`) | Viewer role |
| gatus | `apps/litellm/config.yaml` | App `mcp-gatus`, 8015, built from commit `4c7ed599` | none (no `GATUS_TOKEN`: read-only) | all |

Naming: the LiteLLM `server_name` is the catalog id of the target service, without a
dash, because LiteLLM prefixes each tool with `<server_name>-`. The TrueNAS App and
container that serve it are `mcp-<id>` (`mcp-cyberbro`, `mcp-grafana`, `mcp-gatus`).
A server without an upstream credential is declared in `config.yaml`; one with a
credential goes to the database through `mcp-gateway.sh`.

- The servers share the access group `nabla-mcp`. The client key
  `mcp-claude-code` (`nabla/prod/litellm-mcp-client`) grants that group and no
  LLM model (`no-default-models`).
- Upstream credentials of the database servers are encrypted by LiteLLM with
  `LITELLM_SALT_KEY`; LiteLLM needs no extra env file. Two security contracts
  shaped this: the root installer writes only `runtime/<app>/.env.secrets`, and an
  `env_file` must sit under the runtime directory of its own Compose App.
- The Grafana MCP is its own TrueNAS App, `apps/mcp-grafana` (prefix `mcp-` like
  `mcp-cyberbro`): its runtime file holds only the Viewer token and the bearer
  token (Vaultwarden `nabla/prod/grafana-observability`), never the Grafana admin
  password.
  `sudo bash scripts/truenas/deploy-mcp-grafana.sh --check|--apply` on
  TrueNAS creates it and checks that it refuses a call without the bearer (401).
- `scripts/grafana/mcp-identity.sh check|apply` keeps the Grafana side as code:
  - the admin password lives in Vaultwarden (`nabla/prod/grafana`);
  - the `mcp-readonly` Viewer service account comes from OpenTofu (`infrastructure/grafana`);
  - its token goes straight into Vaultwarden, never into the OpenTofu state.
- `scripts/litellm/mcp-gateway.sh check|apply` (owner terminal, Vaultwarden unlocked):
  - fills `MCP_GRAFANA_SERVER_TOKEN` and installs the `mcp-grafana`
    runtime file with `materialize_runtime.py --ssh truenas`;
  - upserts the homarr and grafana servers through the admin API (`/v1/mcp/server`);
  - mints the client key into `~/.config/nabla/mcp/litellm-gateway.headers` (600).
- `.mcp.json` entry `nabla-mcp`: `scripts/mcp/http-remote.sh` bridges the gateway to
  stdio with `mcp-remote@0.16.5 --header-file`. The Claude desktop app passes no
  shell variable to MCP servers, and no key reaches a command line.
- `scripts/mcp/materialize-keys.sh` rewrites the header files from Vaultwarden on a new workstation.

Other MCP servers of `.mcp.json`, reviewed on 22/11/2026:

| Server | Gateway | Why |
| --- | --- | --- |
| `fastapi-sample` | next | Native HTTP with `X-MCP-Key`. Blocked: `nabla/prod/fastapisample` holds 3 of the 19 fields the manifest declares, so installing Sample's runtime from Vaultwarden would drop its other secrets. Migrate that item first, then add `MCP_OPS_KEY`. |
| `uptime-kuma` | next | Official image `davidfuchs/mcp-uptime-kuma` (streamable HTTP, `MCP_AUTH_TOKEN`). Blocked: no Vaultwarden item holds the Uptime Kuma login. Write tools (delete monitors) need an `allowed_tools` read-only list. |
| `sentry` | later | `@sentry/mcp-server` is stdio only: needs a stdio-to-HTTP bridge App and the `SENTRY_ACCESS_TOKEN` of `nabla/prod/sentry`. |
| `defectdojo` | later | stdio only (FastMCP), 78 tools with deletes: bridge App plus a read-only `allowed_tools` list. |
| `truenas-readonly` | no | Version 2 of the server wants the Docker socket; 1.0.6 stays a TLS-pinned local launcher with a read-only API key. |
| `bitwarden-local` | never | It acts with the owner's unlocked vault (`BW_SESSION`); behind a shared key it would hand every secret to every gateway client. |
| `freshrss-security-readonly` | later | Local script; it would need an HTTP transport and the Cloudflare Access service token on TrueNAS. |
| `context7`, `cloudflare-api` | no | External SaaS with their own authentication (OAuth for Cloudflare): nothing to gain. |

## MCP environment inventory

| Variable | Purpose |
| --- | --- |
| `TRUENAS_MCP_HOST` | TrueNAS 25.10+/26 JSON-RPC host and optional port |
| `TRUENAS_MCP_API_KEY` | dedicated read-only TrueNAS API key |
| `TRUENAS_MCP_INSECURE` | optional self-signed TLS bypass; prefer `false` |
| `HOMARR_MCP_URL` | full Homarr MCP URL |
| `HOMARR_API_KEY` | Homarr API key sent in `ApiKey` header |
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


## Correspondances d'inventaire sécurité (2026-10-20)

Le catalogue v2 possède désormais le système Akvorado (4 composants prévus)
et la ressource ClickHouse partagée ; les relations ntopng/ClickHouse,
Cartography/Neo4j, Scanopy/PostgreSQL et DSOMM/baseline restent en Backstage,
sans copie dans les paramètres Gatus ou Homarr.
Pour la provenance observée, les formats OTel/OCSF et l'export
CycloneDX/OSCAL/OWASP SAMM, voir
[la décision normes et sécurité](../docs/catalog-security-standards.md).


### AutoKuma native Files provider

Le JSON agrégé `apps/autokuma/static/generated-monitors.json` est un
**artefact intermédiaire non monté**, et non un fichier statique AutoKuma
valide. Le runtime monte `/mnt/cpool/autokuma/static-monitors`, rempli à
la demande par `scripts/truenas/render-autokuma-monitors.py --apply` ; un
fichier `nabla-<nabla_monitor_id>.json` par sonde, sans le champ agrégé
`id`. L'identifiant est stable même si le titre Gatus change. Le YAML Gatus
reste l'unique politique de sondes.
