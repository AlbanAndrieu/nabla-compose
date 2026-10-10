# AI stack — upgrade and consolidation plan

Status: **planned / read-only review**, 2026-10-10. No container, dataset,
secret, volume, image, TrueNAS App or deployed configuration was changed.
This document supports the execution index in [roadmap.md](./roadmap.md);
it is **not** runtime acceptance evidence.

## Scope and sources of truth

- Declared source: `apps/*/compose.yml`, catalog relations and runbooks in
  `nabla-compose`. Inspect the PR HEAD, not an old checkout, before changes.
- Actual source: TrueNAS `app.query`, `docker inspect` image IDs/digests,
  effective non-secret configuration, readiness and API smoke.
- Upstream source: pinned release notes and migration documentation. A git
  release tag does **not** prove a compatible OCI image was published.
- Never equate `latest`, `main-stable` or `stable` with an immutable version;
  record the **running digest** and the proposed digest separately.
- Keep all work local-first; no CI reruns for discovery, no automatic merges.
- No data migration, restart, shared-storage move or credential rotation
  without separate operator authorization and a reviewed rollback.

## Upgrade candidates — declared state, not running state

| Group | Declared version | Candidate / gate | Risk |
| --- | --- | --- | --- |
| OpenRAG backend + frontend | `0.7.1` | `0.8.0`, matching images/flows | high |
| Global Langflow | OpenRAG-compatible `0.7.1` image | bundle aligned to OpenRAG `0.8.0` | high |
| OpenRAG OpenSearch | OpenRAG `latest` by default | matching `0.8.0` image and schema | critical |
| Open WebUI | `v0.11.0` | `v0.11.4` | medium |
| Open WebUI Pipelines | Removed from source Compose (unused, operator-confirmed) | runtime retirement separate; preserve volume until reviewed | low |
| Docling Serve CPU | `v1.32.0` | `v1.36.0`; API/OCR smoke | medium |
| LiteLLM TrueNAS | `main-stable` | evaluate `v1.104.2`; verify OCI signature | high |
| LiteLLM GPU workstation | runtime unknown | inspect separately; preserve aliases | high |
| Langfuse web + worker | `4.30.0` | `4.56.0` pair, migration/DB checks | high |
| OpenSearch Security | `2.19.5` | independent security-index plan | critical |
| OpenSearch Dashboards | `3.6.0` | align with **actual** RAG search cluster | high |
| Traefik | `3.7.0` | `3.7.14` security fixes | high |
| Redis | `8.8.0` | `8.10.2` security fixes | high |
| Grafana | `13.1.3` | `13.2.3` security fixes | medium |

Versions discovered on 2026-10-10 from the projects' official GitHub
releases. Revalidate release, image, digest and changelog at execution time.
Remaining services in the 75 Compose app files require the same comparison;
do not infer `upgrade available` from an unpinned tag.


## Operator-confirmed state and proxy decisions (2026-10-10)

- **No ingested data:** Docling, OpenRAG, Wazuh, Keycloak and **OpenSearch
  Security**. Their application/index/identity data migration is **not
  required** at present, conditional on a final read-only check. Do not
  delete other OpenSearch RAG indices without checking: the RAG cluster
  and the distinct `opensearch-security` instance are different workloads.
  Reconfiguration still needs preserved secrets, baseline and rollback.
- **Garage:** stores only the **Terraform state bucket**. It is not a
  general replacement for MinIO without a migration decision. Protect
  state versioning, encryption, concurrency/locking semantics, state
  history and an independent/offsite backup; avoid experimental writes.
- **MinIO:** declared endpoint used by Langfuse for S3 event, media and
  export data (`http://minio:9000`). It should not be removed unless
  Langfuse has an alternative tested endpoint, buckets and migration proof.
  The Compose file currently exposes `9002:9000` and `9091:9001`.
- **AIStor:** distinct MinIO enterprise distribution with a license
  argument `--license /minio.license`; the repository does not declare
  an associated license-file mount. It publishes the **same host ports
  9002 and 9091** as MinIO, so both definitions cannot bind simultaneously
  to the same host addresses. Its `latest` image and evaluation/commercial
  license need explicit review. **Do not deploy in parallel by default**.
- **Nginx Proxy Manager and NPMplus:** both are operator-confirmed trials
  for `hello.int.albandrieu.com`, not authoritative ingress. NPMplus
  was intended to supersede NPM, but did not work. Future ownership
  belongs to Traefik, while pfSense HAProxy remains the explicit
  upstream for directly exposed `*.int` routes. No blind proxy deletion.

### Proposed Traefik + CrowdSec integration (not enabled)

1. **Topology:** pfSense HAProxy (TLS termination and re-encryption)
   → TrueNAS Traefik → application. Existing CrowdSec LAPI is declared
   on `172.17.0.24:8084`, with a separate pfSense bouncer. Define a
   **distinct Traefik bouncer identity/key**; never reuse the pfSense key.
2. **Ingestion:** enable JSON access logging (bounded retention), mount
   only the selected Traefik access log read-only into CrowdSec and
   configure a Traefik acquisition source/parser. Current CrowdSec
   acquisition lists pfSense and Suricata, **not Traefik**.
3. **Enforcement:** evaluate the maintained
   `maxlerebourg/crowdsec-bouncer-traefik-plugin` as a pinned
   Traefik middleware. Load plugin code in an isolated canary first;
   no `latest` plugin or accidental production middleware activation.
   LAPI endpoint `172.17.0.24:8084` is reachable via host port only
   if Docker networking/firewall policies allow it.
4. **Real IP:** pin trusted forwarded headers to the actual pfSense
   HAProxy source addresses (not all RFC1918 ranges). Validate spoofed
   `X-Forwarded-For` rejection, direct LAN traffic, Cloudflare Tunnel
   boundaries and the distinction between CDN/proxy/source identities.
5. **AppSec WAF:** optional **second step**, after plain IP remediation:
   the CrowdSec AppSec listener, collections and bouncer appsec route
   must be separately configured. Start with monitor-only/rule tuning,
   then enable bounded enforcement for a canary.
6. **Canary:** route only `hello.int.albandrieu.com` through Traefik.
   Confirm TLS, backend identity, HAProxy headers, login, false-positive
   rate, response times, Prometheus metrics, CrowdSec decisions and
   rollback. Do not enable CrowdSec middleware globally immediately.
7. **Retire tests:** only after reviewing 30020–30022 and NPMplus
   30360–30362 consumers, certificates, admin UI and data. Keep data
   backups and disable/retire separate TrueNAS apps through its API
   when explicitly approved.

**Security debt surfaced in Traefik Compose:** `--api.insecure=true`
and the HTTP dashboard published at `:8080`; global
`serversTransport.insecureSkipVerify=true`; debug logging; and direct
Docker socket access. Add security-hardening acceptance to the same
Traefik canary, not as an undocumented proxy migration. Prefer the
existing Docker socket proxy only after verifying the required read-only
Docker API capability. Avoid broad configuration changes to the
production entrypoint during the experiment.

Sources: https://docs.crowdsec.net/u/bouncers/traefik/ ,
https://www.crowdsec.net/blog/enhance-docker-compose-security ,
https://docs.crowdsec.net/docs/appsec/intro/ .

## Existing dependencies and potential integration

1. **One Docling extraction API, two clients:** OpenRAG already references
   `http://docling:5001`; Open WebUI has `RAG_EMBEDDING_ENGINE=openai`
   but no declared Docling extraction URL. Check its Docker network: it
   currently has no explicit external `intranet` membership, unlike Docling.
   Evaluate `CONTENT_EXTRACTION_ENGINE=docling` plus
   `DOCLING_SERVER_URL=http://docling:5001` only after DNS and API checks.
   Keep per-client extraction settings; sharing a service does not imply
   sharing knowledge bases or access-control state.
2. **One model gateway where justified:** Open WebUI uses TrueNAS LiteLLM
   at `172.17.0.24:4000/v1` for chat/embeddings; OpenRAG uses the
   workstation directly at `172.17.0.57:4000/v1`. The TrueNAS proxy
   already has `embedding`, `embedding-local` and `workstation-qwen`
   aliases. Evaluate routing both clients through TrueNAS LiteLLM after
   checking latency, streaming, tool-calls, failure isolation and GPU
   workstation offline behavior. **Do not** collapse CPU/GPU embedding
   aliases unless dimensions/model identity are exactly compatible.
3. **Re-use Langfuse before adding LLM tracing tools:** TrueNAS LiteLLM
   already declares `langfuse_otel` callbacks. Inspect whether Open WebUI
   traces through that gateway adequately before adding a UI Filter.
   Avoid duplicated events and accidental prompt/PII capture. Re-use
   Grafana Alloy for infrastructure OTLP telemetry, Tempo for trace
   retention, Prometheus for metrics. Langfuse remains LLM-specific
   evaluation/trace analysis, not a replacement for Grafana.
4. **Re-use OIDC:** Keycloak is repository-managed and backed by shared
   PostgreSQL. Open WebUI supports OIDC. Compare against existing
   Cloudflare Access authentication before enabling Keycloak; choose one
   approved identity chain, verify claims/groups and avoid trusting
   forwarded headers from arbitrary sources.
5. **Re-use tool/search endpoints:** `searxng`, `open-terminal` and the
   LiteLLM `mcp_servers.cyberbro` are already modeled as optional
   integrations. Verify their actual configuration/permissions before
   creating any new search, terminal or MCP server. Terminal and MCP
   actions require least privilege, egress controls and an allowlist.
6. **Do not force one vector store:** OpenRAG uses an OpenSearch index,
   while Open WebUI maintains independent knowledge/permissions.
   Matching embedding model, dimension, chunking, metadata, ACL and
   lifecycle must be proven before any cross-index reuse. Prefer an API
   adapter over directly sharing OpenSearch internal indices.
7. **Shared PostgreSQL / Redis:** use dedicated PostgreSQL databases and
   roles; avoid reusing a superuser. Redis consumers need named ACL
   identities and keys/queues/DB namespaces. Redis logical DB numbers
   alone are not strong security isolation. Never silently reuse another
   application's queue or cache.
8. **Storage reuse is conditional:** Langfuse web/worker references
   MinIO S3 buckets; Garage is already present, and AIStor is declared.
   Evaluate Garage as a backend for Langfuse only after checking
   path-style requests, S3 features, credentials, multipart behavior,
   retention, backup and S3-compatible migration. Bucket moves must
   preserve metadata, access policy and rollback. Keep MinIO until
   Langfuse's data is verifiably moved and restored.

## Duplication decision register

| Candidate | Initial decision | Evidence required before removal |
| --- | --- | --- |
| Open WebUI Pipelines | **Source Compose removed** | TrueNAS runtime retirement and volume cleanup remain separate, non-automatic transactions |
| OpenRAG vs Open WebUI | **Keep separate** | evaluate UX vs ingestion/retrieval boundaries and permissions |
| Gatus vs Uptime Kuma/AutoKuma | **Keep pending** | active probes, alert owners, synthetic checks and recovery path |
| Traefik vs NPM/NPMplus | **Keep pending** | actual ingress ownership, TLS/DNS routes and cert renewal |
| Pi-hole vs AdGuard Home | **Keep pending** | DNS authority, HA, DHCP integration, clients and safe cutover |
| Garage vs MinIO vs AIStor | **Evaluate consolidation** | S3 API/storage semantics, actual buckets, IAM and backup tests |
| OpenSearch RAG vs Security vs Elasticsearch | **Keep isolated** | index owners, plugin compatibility, security isolation and restore |
| Langflow vs n8n | **Keep separate** | AI flows vs business automation, runtime consumers and secrets |
| Prometheus/Gatus/FastAPI outside-in | **Keep separate** | metrics vs LAN health vs public exposure evidence |
| Grafana Alloy vs extra OTel collector | **Reuse Alloy** | OTLP receiver/pipeline tested with existing Tempo/Loki/Mimir |
| Langfuse vs Sentry vs Grafana | **Keep separate** | LLM traces vs errors vs infra metrics/traces |

Nothing is approved for deletion at this stage. Preserve datasets, volumes,
secrets, image digests and history until consumer-free evidence and rollback
have been accepted.

## Candidate new services — minimize additions first

- **RAGAS evaluation job (not an always-on App):** only if Langfuse dataset
  evaluation cannot cover retrieval-grounding, citation quality and
  answer-faithfulness goals. Run as a pinned ephemeral Python job against
  sanitized test documents; store outputs in existing Langfuse/Grafana.
- **Trivy Operator (Talos/Kubernetes, deferred):** assess only once the
  Talos cluster's RBAC and resource baseline is accepted. Avoid another
  scanner if existing image/cluster scanning already provides equivalent
  coverage. Use namespaced, read-only access where possible.
- **Kopia or Restic offsite backup (conditional):** only if a verified
  independent/offsite backup-and-restore capability is absent. ZFS local
  snapshots are not a substitute for offsite recovery. Evaluate encryption,
  credential scope, retention, object-store destination and recovery drills.
- **No new vector DB, alternative Docling/Tika, telemetry collector, auth
  server or reverse proxy** until documented compatibility limitations
  justify it. Existing services already cover these roles.

## Execution waves and acceptance

### Wave 0 — inventory and evidence (no runtime mutations)

- [ ] Capture `app.query` state and effective runtime image digest for
  OpenRAG, Langflow, OpenSearch, Open WebUI, Pipelines, Docling, LiteLLM,
  Langfuse, PostgreSQL, Redis, MinIO, Garage, Gatus and identity services.
- [ ] Produce a version matrix: `declared_tag`, `runtime_tag`,
  `runtime_digest`, `candidate_tag`, `candidate_digest`,
  `release_url`, consumers, persisted volumes and status.
- [ ] Check ports, shared Docker DNS networks, non-secret environment keys,
  provenance, permissions and stateful dependencies.
- [ ] Capture restore proofs, database/API compatibility, snapshot age and
  rollback feasibility without dumping secrets.

**Done:** complete verified matrix, dependency/owner graph and one
restore plan per stateful service. **Defer:** all redeployments.

### Wave 1 — low-risk security and observability

- [ ] Prioritize documented security fixes in Traefik, Redis, Open WebUI
  and other externally exposed services; evaluate impact, not just version.
- [ ] Check `WEBUI_ADMIN_PASSWORD`, `MINIO_ROOT_PASSWORD` and
  `REDIS_AUTH` fallback **without exposing values**. Remove insecure
  defaults only through the canonical secret-migration transaction.
- [ ] Confirm one telemetry route via existing LiteLLM → Langfuse and
  OpenTelemetry → Alloy → Tempo, avoiding duplicate traces.

**Done:** preflight and rollback reviewed, no security regression,
health/permission smoke passes. **Defer:** shared-state migration.

### Wave 2 — Open WebUI integration and simplification

- [ ] Reuse existing Docling Serve after verifying `/ready`, conversion
  API, Docker DNS and supported Docling request format.
- [ ] Upgrade Open WebUI `0.11.0` → `0.11.4` in an isolated test,
  preserving database and file volumes and testing citations/RAG.
- [x] Remove the operator-confirmed unused Pipelines service and its
  unused named-volume declaration from the source Open WebUI Compose.
  This is a source-only change; do not automatically delete the existing
  runtime app or Docker volume, and regenerate catalog projections separately.
- [ ] Confirm no external consumer of TCP/9099 and retire any existing
  Pipelines runtime only through the TrueNAS application lifecycle.
- [ ] Test OIDC via Keycloak/Cloudflare boundary separately.

**Done:** representative PDF/OCR, embeddings, streaming chat, user ACL and
rollback pass. **Defer:** deleting Pipelines until zero consumers proven.

### Wave 3 — coordinated OpenRAG upgrade

- [ ] Qualify `0.8.0` backend/frontend, matching global Langflow image,
  OpenRAG OpenSearch image, built-in flows and version-specific migrations.
- [ ] Compare native LiteLLM provider integration against existing
  `openai` adapter, with GPU `qwen`/`embedding` and offline fallback.
- [ ] Snapshot **both** RAG indices and flow/config/secret references
  before any migration; compare OpenSearch storage/plugin formats.
- [ ] Validate Docling extraction, ingestion/cancel/retry, retrieval,
  source citations and role-based access from a known test document.

**Done:** end-to-end ingest → retrieve → cite + restart + rollback test
passed with model/embedding identity unchanged. **Defer:** vector-index
merging or deleting the OpenRAG-specific dependencies.

### Wave 4 — shared platform and conditional retirements

- [ ] Qualify pinned LiteLLM and Langfuse web/worker releases with their
  PostgreSQL, Redis, ClickHouse and S3 migrations and backups.
- [ ] Compare Garage/MinIO/AIStor features and real bucket consumers.
- [ ] Compare actual Gatus/Uptime Kuma and reverse-proxy routes;
  remove only unused instances after a consumer-free observation period.
- [ ] Decide whether to add any optional evaluation/backup/Kubernetes
  scanner, based on proven unmet requirements rather than catalog breadth.

**Done:** dependency graph updated, no silent owner loss, restored data
and accepted rollback. **Defer:** broad one-shot stack upgrades.

## Official compatibility references

- OpenRAG 0.8.0:
  https://github.com/langflow-ai/openrag/releases/tag/v0.8.0
- Open WebUI 0.11.4:
  https://github.com/open-webui/open-webui/releases/tag/v0.11.4
- Docling Serve 1.36.0:
  https://github.com/docling-project/docling-serve/releases/tag/v1.36.0
- Langflow 1.12.5:
  https://github.com/langflow-ai/langflow/releases/tag/v1.12.5
- Open WebUI Docling integration:
  https://docs.openwebui.com/features/chat-conversations/rag/document-extraction/docling/
- Open WebUI Pipelines deprecation:
  https://docs.openwebui.com/features/extensibility/pipelines/
- Open WebUI SSO:
  https://docs.openwebui.com/features/authentication-access/auth/sso/
- Open WebUI OTLP:
  https://docs.openwebui.com/enterprise/deployment/
- Alloy OTLP support:
  https://grafana.com/docs/alloy/latest/collect/opentelemetry-to-lgtm-stack/
