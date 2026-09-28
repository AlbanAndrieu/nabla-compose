# Homelab roadmap

Last updated: 2026-09-28.

This is the **concise execution index**. Detailed procedures, architecture and
historical evidence live in their canonical documents; see
[`docs/README.md`](./README.md).

Primary references:

- current reboot procedure: [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md);
- incident evidence: [`incidents/`](./incidents/);
- platform migration: [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md);
- secrets migration: [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md);
- security tooling: [`security-inventory-tooling-roadmap.md`](./security-inventory-tooling-roadmap.md);
- service catalog v2: [`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md).

## Dependency automation — Renovate / Mend

Accepted baseline: Renovate is the single routine dependency-PR producer,
ordinary releases use a seven-day cooldown, routine concurrency is bounded to
two branches/PRs, and vulnerability remediation keeps
`dependencies + renovate + security` with a separate two-PR security budget
and no automerge.

Remaining work:

- [ ] Install the hosted Mend Renovate GitHub App for `nabla-compose` and
  `fastapi-sample`, keeping the Actions workflow until hosted execution is proven.
- [ ] Grant Renovate read access to Dependabot alerts and validate one real
  vulnerability-remediation path.
- [ ] Disable Dependabot Security Updates only after Renovate is proven as the
  single security-fix PR producer; keep Dependabot Alerts enabled.
- [ ] Remove the self-hosted Renovate GitHub Actions workflow after hosted-app
  acceptance so dependency maintenance stops consuming Actions credits.
- [ ] Re-enable selective automerge only behind authoritative required checks;
  runtime minor/major, Docker and GitHub Actions updates remain manual by default.
- [ ] Acceptance: no duplicate bot PRs, immediate security remediation, bounded
  concurrency and no automerge without green required validation.

## Current platform state

Accepted baseline:

- Talos `v1.13.9` / Kubernetes `v1.36.3` is 3/3 Ready after reboot;
  TrueNAS VM autostart and the Docker/IPAM/observer-network baseline are proven.
- TrueNAS CSI dynamic provisioning, NFS `publishContext`, cross-worker RWX and
  reclaim are accepted; the historical orphan dataset was successfully removed
  after complete quiesce.
- Sentry end-to-end ingestion is accepted; Suricata captures on `br0` with a
  populated rule set and active `eve.json`.
- Repository-owned storage/config/runtime-secret separation is accepted.
- Security-tooling declarations and the catalog-v2 target architecture are
  versioned; runtime/tool acceptance remains separate.

Active platform debt:

- [ ] Security tooling runtime acceptance for Plumber, NetBox, Dependency-Track,
  DefectDojo and Neo4j; keep Cartography/Scorecard as explicit manual jobs.
- [ ] Add Dependency-Check as the SCA producer; evaluate ArcherySec and Faraday
  as bounded complements while DefectDojo remains the findings system of record.
- [ ] Deploy/accept Docling, run one bounded conversion, then prove OpenRAG
  ingest/retrieve.
- [ ] Finish FastAPI Sentry transaction/span acceptance; error ingestion alone
  is not tracing acceptance.
- [ ] Complete the Grafana native → Compose migration before Mimir / Loki /
  Tempo / Alloy reconciliation.
- [ ] Reconcile Prometheus DOWN targets. Canonical database telemetry is
  PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch; Sybase is excluded.
- [ ] Prove downstream consumption of Suricata `eve.json`.
- [ ] Restore pfSense NetFlow → Cloudflare Network Analytics end to end.
- [ ] Restore repository-owned Uptime Kuma before enabling AutoKuma.
- [ ] Continue staged TrueNAS runtime-env migration; do not bulk-finalize paths
  or recreate non-empty datasets.
- [ ] Resolve Vaultwarden exposure/TLS policy with verified HTTPS, least
  exposure and stricter `/admin` protection.
- [ ] Keep the TrueNAS LXC GitHub Actions runner planned/dormant until needed.

## P0 — controlled TrueNAS reboot accepted

Accepted milestone. The 2026-09-11 reboot transaction proved:

- immutable preparation with `materialize-reboot-bundle.sh`;
- Apps quiesce, workers-before-control-plane shutdown and supported TrueNAS reboot;
- Docker/IPAM/Talos/Kubernetes recovery plus fresh CSI RWX/reclaim validation;
- the historical CSI orphan was successfully removed after complete quiesce;
- manifest-aware resume with deferred non-blocking App debt preserved for
  forensic visibility.

Detailed evidence is retained in
[`incidents/2026-09-11-truenas-reboot.md`](./incidents/2026-09-11-truenas-reboot.md)
and the supported procedure remains
[`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md).

## P0.1 — reboot lifecycle hardening

Accepted: persistent PREPARING/PREPARED state, immutable manifest/bundle
identity, guarded ghost-shim recovery, idempotent resume reconciliation,
declarative lifecycle ordering and explicit deferred-App operator acceptance.

Remaining work:

- [ ] Continue reducing the `no topology mapping` set; use explicit
  `runtime.appId` only where ownership is ambiguous.
- [ ] Move service-specific HTTP/TCP/application readiness into declarative
  lifecycle metadata instead of duplicating readiness logic in scripts.
- [ ] Keep current + previous known-good reboot bundles until another normal
  reboot cycle passes.

### TrueNAS lifecycle phase contract

Required `x-nabla` topology relations remain authoritative. Phases are a secondary barrier for Apps that are simultaneously dependency-ready; they do not override an explicit required dependency.

Startup order:

0. **Bootstrap runtime** — Docker Socket Proxy.
1. **Foundation** — Pi-hole, AdGuard Home, Traefik and Vaultwarden.
2. **Network / edge support** — Cloudflared, DDNS and secondary reverse-proxy tooling.
3. **Primary state** — PostgreSQL, MongoDB, InfluxDB, Redis and Kafka/message-broker equivalents.
4. **Secondary/heavy data** — ClickHouse, OpenSearch, Elasticsearch, MinIO, Garage and other search/object/analytics storage engines.
5. **Platform services** — Graylog, Prometheus/Grafana, CrowdSec, Sentry, Suricata and n8n, subject to explicit dependencies.
6. **Applications** — remaining product, productivity and development workloads.

Shutdown is the exact reverse flattened start order. A failed/non-converged wave blocks later dependency waves but reports all failures inside the current wave. `CRASHED`/`ERROR` is never blindly restarted; `RUNNING` is skipped; `DEPLOYING` is waited on. Historical manifest membership remains immutable; only reviewed ordering/acceptance annotations may evolve.

## P0.2 — CSI hardening

- [x] Dynamic provisioning, controller publishContext, cross-worker RWX and fresh reclaim are green.
- [ ] Make `smoke-truenas-csi-nfs.sh` directly verify bounded TrueNAS NFS share and ZFS dataset disappearance after Kubernetes reclaim.
- [ ] Treat TrueNAS API success as insufficient unless the resource postcondition is also satisfied, especially for NAS-143316.
- [ ] Keep read-only validation separate from write/admin CSI credentials where possible.
- [ ] Harden smoke Pods toward Restricted PSS: `allowPrivilegeEscalation=false`, drop `ALL`, `runAsNonRoot=true`, seccomp `RuntimeDefault`.
- [ ] Evaluate TrueNAS CSI `v1.0.3 -> v1.3.0` only after the reboot baseline is stable.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27.

## P0.3 — TrueNAS storage + runtime secret normalization

Accepted: canonical runtime secret paths, metadata-only secret inventory,
value-blind source comparison, staged copies before finalize, application-dataset
policy and first-wave migration tooling are implemented.

Remaining work:

1. [ ] Accept the first-wave Scanopy/Joplin/AutoKuma migration one service at a
   time; AutoKuma additionally requires Uptime Kuma restored and RUNNING.
2. [ ] Convert remaining explicit legacy `env_file` paths to
   `/mnt/cpool/secrets/runtime/<service>/...`; retire compatibility paths only
   after restart/reboot acceptance.
3. [ ] Classify ignored repository-local `.env` files: secrets to Vaultwarden,
   non-secret settings to tracked config, and remove implicit project-env debt.
4. [ ] Review Apps-preset drift without recreating non-empty datasets merely to
   change presets.
5. [ ] Keep metadata-only inventory current, but defer broad Vaultwarden
   migration until the initialization-control-plane work below is accepted.

## P0.4 — service intent + initialization control plane

Accepted: declarative service intent, initialization audit, durable value-blind
service-state primitives and bounded service migration helpers now exist.

Remaining work:

1. [ ] Add a local-controller profile to FastAPI Sample only after privileged
   routes/authentication fail closed; FastAPI Cloud stays read-only.
2. [ ] Keep `fastapi_observer` read-only; any future mutation adapter requires a
   separate least-privilege identity and no generic shell/`midclt` passthrough.
3. [ ] Extend declarative metadata only where it removes duplicated secret,
   dependency or readiness knowledge; prefer generic `nabla_ops` handlers.
4. [ ] Integrate bounded retry/generic handlers with durable service-state
   transactions and prove operator/runtime acceptance before exposing mutation.
5. [ ] Finish Sample reboot acceptance from canonical secret materialization and
   prove read-only `VM_READ` evidence for the three Talos VMs.
6. [ ] Normalize Sample PostgreSQL ownership to dedicated database/role
   `sample`; never reuse the PostgreSQL superuser.
7. [ ] Resolve the Scrutiny dotenv source conflict value-blind before restaging.
8. [ ] Create currently missing declared datasets only with the corresponding
   service rollout: cyberbro, defectdojo, dependency-track, neo4j and netbox.
9. [ ] Reconcile the live TrueNAS Doco-CD container against the canonical
   `docker-compose-truenas.yml` and verify its effective poll configuration.
10. [ ] Retire the inactive 1Password bootstrap dependency deliberately after
    any still-needed Doco-CD mappings are migrated.

## P0.5 — Vaultwarden migration waves

- Migrate only `active` services by default. `planned` services are migrated when activated; `disabled` services are excluded.
- Wave A: active shared state/foundations (PostgreSQL, Redis, Mongo, OpenSearch, MinIO/Garage/ClickHouse as applicable) with fail-closed secret absence and no known default passwords.
- Wave B: active network/platform/observability consumers (Pi-hole, Traefik, Graylog, Wazuh, Sentry, Nexus, ntopng, Scrutiny) after dependency contracts are explicit.
- Wave C: active AI/RAG consumers (LiteLLM, Langfuse, Langflow, OpenRAG, OpenWebUI) after shared credentials are modeled once rather than duplicated into multiple Vaultwarden items.
- Preserve migration-critical values first; rotate only after runtime + reboot acceptance.
- Keep Vaultwarden bootstrap independently recoverable and keep git-crypt as encrypted secondary recovery until a reviewed retirement decision.

## P1 — infrastructure secrets

1. [ ] OpenTofu/Terragrunt and Garage backend credentials.
2. [ ] Dedicated TrueNAS infrastructure automation identity; never reuse the FastAPI observer identity.
3. [ ] Nexus automation credentials.
4. [ ] Talos/Kubernetes/CSI machine credentials.
5. [ ] Root-owned `0600` runtime rendering under `/mnt/cpool/secrets/runtime/<service>/`.
6. [ ] Retain encrypted recovery material.
7. [ ] Move long-lived machine secrets to Vault/OpenBao only after storage persistence and rollback are proven.

## P2 — platform/security tools

- [ ] Vault/OpenBao after CSI/reboot acceptance.
- [ ] Falco after infrastructure baseline stabilizes.
- [ ] Kubara config/bootstrap.
- [ ] Traefik/Kubara ingress with an explicit bare-metal exposure model.
- [ ] FastAPI Kubernetes smoke using an immutable image and `test.int.albandrieu.com` after storage and ingress ownership are stable.

### P2.1 — security inventory, supply-chain and attack-graph tooling

The v2 normalization decision supersedes the earlier plan to keep the complete
catalog schema inside `x-nabla`.

Target contract:

- native Backstage descriptors own entity identity, owner/system/lifecycle and
  standard relations;
- Compose owns runtime facts;
- Backstage qualified labels own operational intent; minimal `x-nabla` is reserved for exceptional `after/before/wants`, rare relation enrichment, structured risk acceptances, and temporary desired exposure/security intent when a provider is not yet Git/IaC-managed;
- OpenTelemetry semantics align runtime service identity and operational criticality;
- Backstage BIA annotations + a calculated `albandrieu.com/business-criticality` label own business criticality separately from operational criticality;
- CycloneDX/Trivy owns service/package supply-chain projection;
- Cartography/Neo4j owns observed graph correlation, not lifecycle authority.

Detailed cutover: `docs/service-catalog-v2-normalization.md`.

#### P2.1.a — prepare the migration without changing runtime behavior

- [ ] Freeze the legacy v1 contract as migration input: inventory every service,
  entity ID, dependency, public/LAN hostname, desired visibility,
  `cloudflareAccessRequired`, accepted security exception, runtime binding,
  lifecycle wave and consumer.
- [x] Generate a machine-readable **v1 -> v2 parity report** with a verified
  `byEntityRef` index for materialized Backstage identities; unresolved legacy
  identities remain explicit debt and are never silently joined by display name.
- [ ] Define/validate the v2 schemas and conventions:
  Backstage descriptors, entity-ref labels, named Compose ports,
  temporary Gateway-like `x-nabla.exposure`, exceptional
  `boot.after/before/wants`, risk acceptances, Kubernetes-style conditions,
  and the BIA/business-criticality policy (`DMTP/MTPD`, RTO, RPO, OMCA/MBCO,
  impact dimensions and provisional/validated assessment status).
- [ ] Add anti-duplication validation: detect and report compatibility debt
  during preparation while v1 must coexist; the strict cutover gate rejects a
  fact/relation declared in more than one authority (for example Backstage
  `dependsOn` plus x-nabla alias, or Traefik hostname plus duplicate x-nabla
  exposure).
- [x] Add `catalog/business-criticality-policy.yaml` plus local validation that
  derives `low | medium | high | critical` from the strictest BIA driver; the
  numeric/time thresholds are explicit Nabla policy, not claimed as ISO/NIST
  thresholds.
- [x] Keep the current reboot wave planner and both legacy exposure JSON files
  operational during preparation; no runtime behavior changes in this phase.

**Gate P2.1.a:** the parity inventory is complete and the migration tooling can
explain where every legacy field will move without deleting anything.

#### P2.1.b — prove the model on representative services

- [x] Migrate a bounded pilot set covering the main patterns:
  `neo4j` (stateful Resource), `cartography` (manual job + dependency),
  `postgresql` (shared data Resource), `sample` (internal + Cloudflare
  desired exposure), and `traefik` (Git-native route provider).
- [x] Add/review `catalog-info.yaml`, Compose project names, entity-ref labels
  and named long-syntax ports for the pilot. The local contract validates
  Backstage graph refs, identity collisions, named backend ports and temporary
  desired-exposure security intent.
- [x] Add provisional BIA profiles to the representative Backstage pilot and
  keep business criticality distinct from `operational-criticality` / OTel
  `service.criticality`; validate `RTO < DMTP`, ISO-8601 duration syntax and
  declared-vs-calculated tier consistency locally.
- [ ] Demonstrate that provider outages preserve desired intent:
  Cloudflare/Docker/TrueNAS unavailable => hostname/visibility/Access intent
  remains present while observed conditions become `Unknown`.
- [ ] Prove the first dependency-DAG/readiness plan against the pilot without
  removing the legacy wave planner.

**Gate P2.1.b:** pilot v2 projection and v1 behavior are semantically equivalent
for identity, dependencies, exposure intent and reboot safety.

#### P2.1.c — bulk migrate nabla-compose

- [ ] Generate/review all `apps/**/catalog-info.yaml`.
- [x] Add deterministic Backstage materialization-debt inventory for generated
  services. Initial post-#215 baseline: 118 generated services, 5 materialized,
  113 remaining (104 active, 7 planned, 2 disabled). Prioritize the active
  `critical/high` subset before medium/low/unclassified debt; absence of
  legacy `status` means `active` by the v1 contract. The first bulk waves now
  materialize the core security/data services plus Garage; `pfSense`,
  `TrueNAS` and `Docker` are intentionally represented as root static
  Backstage Resources instead of creating misleading app-local descriptors from
  their legacy `sourcePath` aliases. The active `medium` wave now includes
  Nexus, AutoXpose, Portracker, Pyroscope, Code Server and AIStor with Backstage
  identities and runtime correlation labels; newly touched Compose services use
  stable project names and named LAN-bound ports where applicable. AutoXpose
  also declares its cross-project dependency on
  `component:default/docker-socket-proxy`. The current #218 follow-up adds
  InfluxDB + Scrutiny, Plumber/API/worker, Dockhand, Dozzle, LanguageTool,
  Joplin, Docling, Homarr/reconciler, Home Assistant, legacy Nginx Proxy
  Manager, OpenHands and Squid as reviewed dependency groups. Active
  `critical/high/medium` materialization debt is now **zero**. This PR resolves
  the remaining Doco-CD authority debt: workstation `docker-compose.yml` no
  longer authors its catalog metadata, TrueNAS `docker-compose-truenas.yml`
  owns `x-nabla` + runtime entity-ref, generated catalog/topology evidence now
  points to that TrueNAS source, and `component:default/doco-cd` captures the
  required Docker Socket Proxy dependency. The guided
  OpenWebUI BIA/materialization in #218 reduced the remaining active debt to
  45 lower-priority services: 40 unclassified and 5 low. This PR now
  materializes the complete low-criticality wave — Draw.io, Hello Nginx,
  OpenClaw Sandbox, OpenSSF Scorecard and WordPress — with stable Compose
  project names, runtime entity-ref labels, provisional low BIA profiles and
  named HTTP ports where applicable. WordPress additionally removes invalid
  cross-project Compose `depends_on: postgres`: its init container owns the
  bounded readiness loop on the external `intranet` network while Backstage
  owns the required dependency on `resource:default/postgresql`. Remaining
  active Backstage materialization debt is therefore **36 services**, all
  currently **unclassified**, with zero low/medium/high/critical services. This
  count is derived by matching generated active service IDs to actual Backstage
  `metadata.name` values, not merely by checking whether an app directory
  contains some descriptor. Recompute it before each wave with
  `python scripts/audit-service-catalog-v2-parity.py --check --debt-json`;
  do not maintain the count independently. Because all remaining entries are
  unclassified, the next waves are classification-first: inspect one coherent
  runtime group, establish evidence for criticality/BIA, and only then
  materialize reviewed entities. Nginx Proxy
  Manager remains operationally active but is explicitly modeled with Backstage
  `lifecycle: deprecated` while the NPMplus migration proceeds.
- [ ] Complete a BIA pass for every business-relevant Component/Resource:
  replace provisional values with reviewed DMTP/MTPD (DIMA/DMIA business
  concept), RTO, applicable RPO, OMCA/MBCO and impact dimensions; keep
  `bia-status=provisional` until an owner has reviewed the assumptions.
- [ ] Validate the provisional OpenWebUI BIA: reviewed targets are
  MTPD/DMTP=`P7D`, RTO=`P1D`, RPO=`P1D` (objective, not yet proven), with
  a **3-day recovery escalation threshold**. The MBCO requires the OpenWebUI UI
  on the LAN plus LiteLLM, OpenRAG and a working OpenAI-compatible GPU inference
  capability; Cloudflare Tunnel is not continuity-critical. Conversations and
  OpenRAG-derived content are highly sensitive, prompt/history loss within the
  RPO is acceptable, and configuration recovery is mandatory.
  - [ ] **Backup implementation:** resolve the real OpenWebUI/OpenRAG datasets,
    schedule OpenWebUI snapshots <=12h, add encrypted/off-pool backup or
    replication <=24h, include OpenRAG documents/config/keys/data and either
    migrate or explicitly back up the OpenWebUI Pipelines named volume.
  - [ ] **Backup monitoring:** alert when the newest local recovery point or
    independent successful backup exceeds 24h; retain evidence without secret
    values or sensitive prompt/document content.
  - [ ] **PRA drill:** restore to an isolated path/environment, then prove LAN UI
    login, configuration, one LiteLLM chat request, one OpenRAG retrieval and one
    GPU-backed OpenAI-compatible inference request. Cloudflare validation is a
    separate non-blocking step after LAN acceptance.
  - [ ] **Recovery objectives:** record achieved RTO/RPO; target restoration is
    <=1 day, escalate recovery/rebuild/alternate-GPU actions at 3 days, and keep
    the 7-day DMTP as the absolute tolerable-disruption boundary.
  - [ ] **BIA acceptance:** only change `bia-status` from `provisional` after
    backup freshness and a non-destructive restore drill are evidenced and
    owner-reviewed.
  Run `sudo bash scripts/truenas/diagnose-openwebui-backup-pra.sh --check`
  before implementation to inventory the real dataset, latest snapshot,
  independent replication/cloud backup, recent successful backup age,
  encryption evidence, OpenRAG recovery paths and Pipelines volume debt. Until
  that check is green, RPO=`P1D` remains an objective rather than an achieved
  control. Detailed procedure: `docs/openwebui-backup-pra.md`.
- [x] Materialize LiteLLM and OpenRAG as Backstage entities and model
  OpenWebUI's required continuity dependencies with canonical `spec.dependsOn`.
  A logical `resource:default/gpu-openai-compatible-inference` now represents
  the required GPU capability without binding continuity to the intermittent
  workstation; keep the current legacy relation only as a temporary v1
  compatibility projection until the one-shot topology cutover.
- [x] Enforce explicit BIA ownership for every materialized Backstage
  `Component` / `Resource`: `operational-state` is mandatory; active
  entities must choose `bia-scope=direct|inherited`; direct entities require a
  complete BIA (and stateful direct types require RPO), while inherited
  entities must not duplicate their own business-criticality/BIA and must be
  justified either by `spec.subcomponentOf` or by at least one incoming
  Backstage `dependsOn`. Unknown operational-state values fail closed instead
  of bypassing BIA coverage. Planned/disabled entities may remain incomplete
  until activated.
- [x] Propagate dependency criticality as a separate derived read-model signal:
  `effectiveDependencyCriticality` walks required Backstage `dependsOn`
  edges transitively, preserves `ownBusinessCriticality`, reports
  `inheritedFrom`, and fails closed on duplicate/unresolved graph identity.
  It never rewrites the Resource's own BIA.
- [ ] For every `high` / `critical` business entity, link the BIA to a concrete
  PCA/PRA/DRP recovery test plan and evidence: restore/bascule scenario, expected
  RTO/RPO, minimum continuity objective and last successful exercise. A valid
  catalog calculation is not continuity acceptance by itself.
- [ ] Normalize Compose project/service identity, named ports, healthchecks and
  native `depends_on`; remove redundant `container_name` only where safe.
- [ ] Remove direct privileged Docker socket access where practical. Dockhand,
  Dozzle and OpenHands currently depend on `resource:default/docker` because
  their management/actions/shell or sandbox features require broader access than
  the existing read-only `docker-socket-proxy`; evaluate separately scoped
  proxies or disable privileged features before changing runtime behavior.
- [ ] Migrate every legacy desired hostname/visibility/Access requirement to
  Traefik/Gateway/provider IaC or temporary `x-nabla.exposure`.
- [ ] Migrate every accepted exposure/security exception to structured
  `riskAcceptances`.
- [ ] Remove duplicated catalog/runtime/relation fields from `x-nabla`.
- [ ] Replace phase/priority/wave authoring with dependency DAG + readiness;
  keep only exceptional systemd-style ordering metadata.
- [ ] Generate Backstage/CycloneDX projections and the parity report; do not
  generate a new canonical flat exposure catalog.

**Gate P2.1.c:** 100% desired-intent parity, zero unresolved entity refs, zero
duplicate authorities, zero Backstage materialization debt, zero active-entity
BIA-scope/coverage errors, stateful direct-RPO coverage, and no legacy fact
without an explicit v2 disposition. Own BIA and effective dependency criticality
must remain separately explainable.

#### P2.1.d — prepare consumers before destructive cutover

- [ ] Prepare FastAPI to consume Backstage desired state plus provider/runtime
  observations separately and expose Kubernetes-style conditions.
- [ ] Expose both `operationalCriticality` and BIA-derived
  `businessCriticality` (plus DMTP/RTO/RPO/recovery margin and assessment
  status) in FastAPI without collapsing them into one severity.
- [ ] Prepare Site Alban to consume entity refs and the new resource-oriented
  FastAPI views; keep icons/layout presentation-only.
- [ ] Keep any FastAPI/Site cold-start snapshot generated/cache-only and prove
  that provider unavailability does not erase desired exposure intent.
- [ ] Run local-first quality gates in all three repositories; do not depend on
  GitHub Actions credits for deterministic formatting/lint/test feedback.

**Gate P2.1.d:** all three PRs are ready together; legacy readers are no longer
required for normal execution.

#### P2.1.e — coordinated one-shot cutover

- [ ] Merge/deploy the prepared `nabla-compose` v2 contract.
- [ ] Immediately deploy the prepared FastAPI consumer.
- [ ] Immediately deploy the prepared Site Alban consumer.
- [ ] Run cross-repository smoke for entity refs, desired-vs-observed exposure,
  health/status conditions, topology rendering and reboot planning.
- [ ] Verify representative internal route, Cloudflare Tunnel + Access route,
  direct pfSense/HAProxy route and Kubernetes route if present.

**Gate P2.1.e:** all consumers operate exclusively on v2 semantics and the
desired exposure intent remains visible with providers both healthy and
unavailable.

#### P2.1.f — remove legacy contracts and prove reboot acceptance

- [ ] Delete `homelab-services.json`,
  `homelab-exposure-overrides.json`, legacy generated
  `services.json/service-topology.json` and obsolete compatibility code only
  after the parity/smoke gates are green.
- [ ] Replace the legacy resume-wave implementation with dependency-DAG +
  readiness reconciliation.
- [ ] Run one controlled TrueNAS reboot and require equivalent-or-better
  acceptance before deleting the old planner.
- [ ] Keep rollback evidence/artifacts until post-cutover acceptance is complete.

**Gate P2.1.f:** no runtime or UI path depends on the legacy flat schemas or wave
metadata.

#### P2.1.g — later provider-native IaC cleanup

- [ ] Move Cloudflare Tunnel/Access desired state from temporary
  `x-nabla.exposure` into OpenTofu/Terraform when that control plane is
  introduced.
- [ ] Move pfSense/HAProxy desired routes into a reviewed declarative/API-managed
  source when safe automation exists.
- [ ] Use native Gateway API for Kubernetes-hosted routes.
- [ ] Delete each temporary `x-nabla.exposure` entry as soon as the provider has
  a real Git/IaC desired-state source; FastAPI continues to expose provider
  observation as status.

**Gate P2.1.g:** `x-nabla.exposure` remains only for providers that genuinely
lack a native/declarative desired-state source.

- [ ] **Backstage-native authoring:** bulk-generate/review `apps/**/catalog-info.yaml` from the current v1 catalog, then make those descriptors canonical in the same breaking cutover.
- [ ] **Compose normalization:** add top-level project names, one reverse-DNS entity-ref label per managed service, derive image/network/port/profile/health/dependency facts from Compose, and remove redundant `x-nabla` copies.
- [ ] **x-nabla v2 reduction:** reserve Backstage `spec.lifecycle` for `experimental | production | deprecated`; delete boot phase/priority/target/wave metadata, derive required ordering from Backstage `spec.dependsOn` + Compose `depends_on` + readiness, and retain only exceptional systemd-inspired `after/before/wants` plus non-duplicative relation/risk metadata.
- [ ] **Static infrastructure normalization:** replace `service-topology.static.json` + legacy service-file references with Backstage static entities; preserve desired exposure/security intent in Git until each provider has native IaC, and derive only observed endpoint/route/runtime status from providers.
- [ ] **One-shot generated contracts:** emit Backstage entity/relationship projections and CycloneDX 1.7 with one `catalogRevision`; do not generate a replacement flat exposure catalog.
- [ ] **FastAPI one-shot cutover:** delete `homelab-services.json` and `homelab-exposure-overrides.json` only after desired-intent parity is proven; consume Backstage + provider-native/temporary Git route intent as spec-like desired state and Compose/TrueNAS/Kubernetes/Traefik/Cloudflare/pfSense observations as status-like evidence, normalize conditions, and key all joins by full entity ref.
- [ ] **Site Alban one-shot cutover:** replace its old service/topology DTOs and bundled flat fallback, use full entity refs as React Flow IDs, consume FastAPI resource-oriented runtime/network views, and keep icons/layout presentation-only.
- [ ] **Cross-repository gate:** prepare all three PRs before cutover and require revision parity, no unresolved refs, no display-name joins, no unstructured exposure exceptions, and a parity report proving every current public hostname / visibility / Access requirement / accepted exposure exception has a v2 declared home before deleting the legacy JSON.
- [ ] **Security evidence flow:** prove one representative `Trivy -> CycloneDX -> Dependency-Track` path, one scanner/Trivy import into DefectDojo and one bounded Neo4j/Cartography rule joining service identity to exposure/vulnerability evidence.
- [ ] Normalize NIST CSF 2.0 classifications to `Govern | Identify | Protect | Detect | Respond | Recover` and project service criticality to the OpenTelemetry `service.criticality` vocabulary.

Runtime preparation contract for this wave:

1. `scripts/truenas/prepare-security-tooling-secrets.sh --apply <app|all>` renders the exact Vaultwarden item into `/mnt/cpool/secrets/runtime/<service>/.env.secrets` as `root:root 0600`.
2. `--verify-vaultwarden` proves byte-for-byte parity between the unlocked Vaultwarden item and the runtime materialization without printing values.
3. `scripts/truenas/bootstrap-security-tooling-postgres.sh --apply <app>` idempotently creates/rotates dedicated shared-PostgreSQL roles and databases for Plumber, NetBox, Dependency-Track and DefectDojo, then proves authentication.
4. `scripts/truenas/deploy-security-tooling.sh --apply <app|all>` validates Compose/catalog contracts, storage, database prerequisites, reconciles the TrueNAS Custom App, waits for middleware `RUNNING`, validates container stability and probes the service HTTP endpoint.
5. Cartography and Scorecard remain `profile: manual` jobs: validate their Compose/secrets but do not register them as always-on TrueNAS Apps or reboot obligations.
6. Until catalog v2 is implemented, keep the current topology-derived resume waves as the accepted runtime contract. During v2 cutover, replace them with dependency-DAG + readiness reconciliation and prove equivalent reboot acceptance before removing the legacy wave planner.


- [ ] **NetBox** — Compose/catalog and runtime bootstrap are prepared; deploy and accept [netbox-community/netbox](https://github.com/netbox-community/netbox) for network/infrastructure source-of-truth use cases: IPAM, VLANs, prefixes, devices/VMs, interfaces and infrastructure ownership. Backstage owns service/catalog identity; NetBox owns network/infrastructure intent; reconciliation uses stable entity/infrastructure IDs.
- [ ] **OWASP DefectDojo** — Compose/catalog and runtime bootstrap are prepared; deploy [DefectDojo](https://github.com/DefectDojo/django-DefectDojo) as the normalized vulnerability/finding aggregation layer. Ingest selected SAST, SCA, secrets, IaC, container, DAST and infrastructure scanner outputs through import/reimport/API; validate deduplication and preserve scanner evidence instead of treating DefectDojo as an asset source of truth.
- [ ] **OWASP Dependency-Track** — Compose/catalog and runtime bootstrap are prepared; deploy [Dependency-Track](https://github.com/DependencyTrack/dependency-track) for CycloneDX SBOM/component inventory, software-supply-chain risk and vulnerability tracking. Start with one representative service, generate/import an SBOM, then reconcile component/project identity with the canonical Nabla service ID. Reference implementation guide: [Stéphane Robert — Dependency-Track](https://blog.stephane-robert.info/docs/securiser/analyser-code/dependency-track/).
- [ ] **OpenSSF Scorecard** — manual-job Compose and Vaultwarden contract are prepared; integrate [OpenSSF Scorecard](https://github.com/ossf/scorecard) for repository and upstream dependency security-health checks. Keep Scorecard findings as supply-chain posture evidence, not as an overall service-risk score; export relevant results into the vulnerability/security reporting path.
- [ ] **Cartography + Neo4j attack graph PoC** — Neo4j persistent-App bootstrap and Cartography manual-job secret contract are prepared; evaluate [cartography-cncf/cartography](https://github.com/cartography-cncf/cartography) backed by [Neo4j](https://neo4j.com/) only after the normalized Backstage/Compose identity model is stable. Ingest GitHub, Kubernetes, cloud/identity/security sources, correlate through explicit entity refs/image digests/infrastructure IDs, and prove bounded Cypher queries for attack paths, internet exposure, privilege relationships and blast-radius analysis. Do not make Neo4j a second CMDB or use inferred graph edges to alter lifecycle ordering automatically.
- [ ] Define the final interoperability contract: Backstage = catalog identity/standard relations; Compose = desired runtime; minimal `x-nabla` = Nabla-only operational/security policy; NetBox = network/infrastructure intent; Dependency-Track = components/SBOM; DefectDojo = normalized security findings; Scorecard = repository/upstream posture; Cartography/Neo4j = relationship/attack-path analysis. Reconciliation must use stable entity refs/digests/infrastructure IDs and preserve provenance/evidence.

## P2.2 — multi-cluster GPU foundation with Karmada

Goal: keep the current TrueNAS-hosted Talos cluster as the stable always-on home platform while making compute capacity extensible to an intermittent Ubuntu workstation GPU cluster and, later, a GPU-capable cloud Kubernetes cluster from a provider that is intentionally not selected yet.

Target control-plane placement:

- **Karmada management plane must be always on.** Do not host it on the workstation and do not make it depend on a future cloud provider.
- Preferred target: a **small dedicated Kubernetes management cluster/VM hosted on TrueNAS**, separate from member workloads and failure domains. A single small management node is acceptable for the first homelab PoC; move to a more redundant management plane only if Karmada becomes operationally critical.
- The existing `nabla-talos` cluster remains a member cluster and continues to own the always-on baseline services.
- The Ubuntu workstation becomes a separate Kubernetes member cluster with GPU capability. It is explicitly **intermittent/opportunistic capacity** because the workstation is normally powered off.
- A future cloud member cluster provides elastic/remote GPU capacity. Provider choice remains open until GPU type, cost, networking, managed-Kubernetes constraints and scale-to-zero behavior are compared.

Implementation stages:

1. [ ] Keep Karmada out of the current bootstrap critical path until CSI, ingress, baseline policy/security and the single-cluster smoke path are stable.
2. [ ] Define stable cluster identity/labels before federation, including location, provider, GPU capability/type, power profile, cost class and workload class.
3. [ ] Create the dedicated always-on management Kubernetes VM/cluster on TrueNAS and deploy a pinned/tested Karmada release there.
4. [ ] Register `nabla-talos` as the first member without moving existing workloads under Karmada control; prove inventory/readiness, then one bounded stateless propagation smoke.
5. [ ] Build the Ubuntu workstation Kubernetes cluster separately, validate NVIDIA runtime/device exposure, then register it as `workstation-gpu`. Offline state must be expected and must not make the home platform unhealthy.
6. [ ] Add placement policy so workstation GPU capacity is used only for suitable stateless/batch/AI workloads; never place mandatory state or quorum exclusively there.
7. [ ] Select a cloud GPU provider only after comparing GPU SKUs, Kubernetes offering, networking/egress, storage, startup latency, scale-to-zero and cost controls.
8. [ ] Define workstation/cloud fallback for GPU jobs while keeping ordinary services pinned to the always-on home cluster unless they have a reviewed multi-cluster SLO.
9. [ ] Keep storage portable across clusters; do not assume TrueNAS NFS is appropriate/reachable for workstation/cloud members.
10. [ ] Keep networking explicit; Karmada placement does not imply transparent cross-cluster pod networking.
11. [ ] Keep secrets out of propagation policy source; use dedicated least-privilege member credentials and keep the Karmada API private.
12. [ ] Acceptance smoke: one stateless workload on `nabla-talos`, one GPU workload on the workstation when online, workstation shutdown without degrading mandatory home services, then repeat with cloud GPU capacity.

Karmada remains a federation/control plane above independent Kubernetes clusters, not a mechanism to stretch the current Talos cluster across intermittent/WAN nodes.

## P3 — runtime/services

- [x] Prometheus, Grafana, Graylog baseline, Langflow, Wazuh core and OpenRAG core exist.
- [ ] CrowdSec is tracked with `status: planned`; it is not yet used/runtime-accepted and must not be treated as an expected running service until explicitly activated.
- [x] Langfuse post-reboot runtime acceptance: web/database and worker checks are green.
- [x] **Sentry Taskbroker/Kafka/Relay recovery accepted** — Taskbroker bootability restored, Taskworker→Taskbroker gRPC reachable, Kafka `taskworker` consumer rejoined and drained to lag `1`, Relay project-config path recovered, and the full synthetic event is persisted in ClickHouse. Recovery required no offset reset, topic deletion, SQLite deletion, Kafka restart or whole-App redeploy.
- [ ] **Sentry upstream/version debt** — monitor self-hosted 26.8 Taskbroker Kafka coordinator/session-timeout/rejoin behavior. Functional health must include Taskworker→Taskbroker reachability, active Kafka membership/lag and end-to-end ingestion; process/container health alone is insufficient.
- [ ] **Sentry ↔ GitHub integration** — configure the self-hosted Sentry GitHub integration at `https://sentry.albandrieu.com/settings/sentry/integrations/github/`, authorize only the required `AlbanAndrieu` repositories with least privilege, verify repository mapping, then prove that a controlled Sentry issue can resolve the relevant GitHub source/commit/PR context before marking the integration accepted.
- [x] **Exporter conflict preflight** — TrueNAS native reporting/Netdata and ports `8125/9125/9102/9308` were inventoried; no listener/publisher conflict exists. StatsD remains deferred and is no longer part of incident recovery. Kafka exporter remains with `apps/kafka` and must be deployed only in a controlled Kafka App update window after preserving the accepted Sentry functional baseline.

### Cyberbro provider/account onboarding

- [x] Create the Vaultwarden application item `nabla/prod/cyberbro` with all 27 optional secret mappings and prove a `0600` render without exposing values.
- [ ] Deploy/accept the Cyberbro free-engine UI/API + MCP baseline before adding external provider credentials.
- [ ] Create or validate dedicated homelab accounts/API identities for AbuseIPDB, AlienVault OTX, Criminal IP, CrowdStrike Falcon, DFIR-IRIS, Google Programmable Search, Google Safe Browsing, Hister, ipapi, IPinfo, Microsoft Defender for Endpoint, MISP/MISP feedback, OpenCTI, Ransomware.live, ReversingLabs Analyze, Rosti, Shodan, Spur, ThreatFox, VirusTotal and WebScout. `PROXY_URL` is configuration-only, not a provider account.
- [ ] Onboard providers in bounded batches, starting with lower-risk reputation APIs, then self-hosted integrations, then enterprise tenant integrations; validate the corresponding Cyberbro engine after each batch.
- [ ] Review provider quotas/rate limits and least-privilege scopes before increasing MCP/LiteLLM-driven automation. Detailed checklist: `docs/cyberbro-provider-onboarding.md`.
- [ ] **Vaultwarden token-refresh debt** — if the transient Cloudflare `502 origin_bad_gateway` recurs, correlate Cloudflare/tunnel/reverse-proxy timing with Vaultwarden `/identity/connect/token` latency. A completed create/edit followed only by failed `bw sync` is warning-only and must not trigger a blind re-apply.
- [ ] **Vaultwarden icon TLS debt** — identify the item/URI or redirect that causes icon fetching against `82.66.4.247`; replace raw-IP HTTPS with a DNS name covered by `*.int.albandrieu.com` or suppress that icon-fetch path. Keep TLS verification enabled.

### Grafana native → Compose migration

Do this before enabling/reconciling Mimir / Loki / Tempo / Alloy from `apps/grafana/compose.yml`.

1. [ ] Run `sudo bash scripts/truenas/diagnose-grafana-migration.sh --check` while the native Grafana App still exists.
2. [ ] Verify `/mnt/cpool/grafana/data/grafana.db` opens read-only and record the dashboard/datasource counts plus a representative sample of dashboard UIDs/titles and datasource UIDs/types/URLs. Do not export datasource credentials.
3. [ ] Resolve the actual ZFS dataset backing `/mnt/cpool/grafana/data` (`findmnt -T` + `zfs list`) and take a reviewed `@pre-grafana-compose-20260912` snapshot before deleting the native App.
4. [ ] Preserve `/mnt/cpool/grafana/data`, `/mnt/cpool/grafana/data/grafana.db` and `/mnt/cpool/grafana/plugin`; never select an App-removal option that deletes the backing data/dataset.
5. [ ] Stop/remove only the native Grafana App after the evidence and snapshot exist; verify `172.17.0.24:30037` is free.
6. [ ] Start only the repository Grafana service first (`docker compose -f apps/grafana/compose.yml up -d --no-deps grafana`) on `${GRAFANA_PORT:-30037}:3000`, UID/GID `568`, reusing `/mnt/cpool/grafana/data:/var/lib/grafana`.
7. [ ] Verify `GET http://127.0.0.1:30037/api/health`, then verify representative restored dashboard UIDs/titles and datasource definitions against the pre-migration inventory.
8. [ ] Keep the pre-migration snapshot and original data until Grafana acceptance is complete; rollback means stop the Compose Grafana, restore the reviewed dataset snapshot if required, and do not mutate Mimir/Loki/Tempo/Alloy as part of the Grafana rollback.
9. [ ] Only after Grafana is accepted, reconcile/start Mimir / Loki / Tempo / Alloy and run the full observability-stack validation.

- [ ] **Prometheus DOWN-target reconciliation** — Sybase is excluded by design. Canonical database telemetry is PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch. Diagnose/repair those jobs from Prometheus `lastError` plus listener/owner evidence. Keep HAProxy `:9101` as the pfSense HAProxy exporter and prove its runtime `PFSENSE_HAPROXY_SCRAPE_URI` reads the pfSense HAProxy statistics endpoint. Defer Alloy/Mimir/Loki/Tempo target acceptance until the Grafana migration above is green.
- [x] **Suricata capture + rules/EVE acceptance** — engine RUNNING on TrueNAS `br0`; persistent rules file populated; ~52k rules load; alerts generated; `eve.json` active.
- [ ] **Suricata downstream consumption** — prove CrowdSec/Alloy/central observability consumes current EVE and monitor kernel drops/rule refresh health.
- [ ] **pfSense NetFlow → Cloudflare Network Analytics** — restore flow export path and prove fresh flow arrival end to end.
- [ ] Scrutiny: finish TrueNAS SMART acceptance plus workstation collector with pinned v0.9.3 collector.
- [ ] **Joplin Server** — deploy `apps/joplin/compose.yml`, bootstrap the dedicated shared-PostgreSQL role/database, change the bootstrap administrator credentials and validate `/api/ping` plus client sync through `joplin.int.albandrieu.com`.
- [ ] **Uptime Kuma + AutoKuma Compose** — add repository-owned Uptime Kuma on host port `31050`; AutoKuma remains only the declarative reconciler and stays stopped while Kuma is absent.
- [ ] **Homarr bootstrap** — make first-run initialization idempotent and secret-backed, then apply generated topology through `homarr-sync`.
- [ ] **Native TrueNAS → Compose migration** — PostgreSQL and AdGuard Home remain native TrueNAS Apps until backup/rollback/consumer validation is designed.
- [ ] **Deferred: nginx-proxy-manager** — investigate persistent `DEPLOYING` / unhealthy state.
- [ ] **Deferred: OpenArchiver** — restore saved App or formally remove from runtime intent after review.
- [ ] **Deferred: Paperless-ngx** — restore health, then refactor dedicated PostgreSQL/Redis toward shared services with migration/rollback.
- [ ] Akvorado ingestion/query acceptance.
- [ ] ntopng reconciliation after Suricata.
- [ ] Pi-hole post-reboot functional acceptance: DNS, UI/API, `pihole-dns-sync`, exporter, no restart loop.
- [ ] Build a derived immutable code-server image; remove startup-time package provisioning.
- [ ] **Docling/OpenRAG** — restore `docling-serve`, prove API/health and one bounded document ingestion, then continue OpenRAG ↔ workstation LiteLLM/GPU routing.

## P3.1 — FastAPI homelab observer

Keep FastAPI as an observer, not an appliance recovery controller.

- [ ] Prove TrueNAS, pfSense, Cloudflare, Prometheus, Sentry and Pyroscope transport/auth/application results independently.
- [ ] **FastAPI Sentry tracing acceptance:** deploy the route-based transaction naming from `fastapi-sample#251`, run `scripts/truenas/smoke-fastapi-observability.sh`, and require one `/sentry-debug` event in project `2` whose stored `trace_id` matches the injected trace plus at least one corresponding row in `eap_spans_local` or `transactions_local`. Error ingestion without a persisted transaction/span is not tracing acceptance.
- [ ] **Pyroscope runtime acceptance:** require `/ready` success plus recent Pyroscope series for `service_name="fastapi-sample"`; keep process profiling independent from Sentry availability so one telemetry backend cannot disable the other.
- [ ] **Prometheus FastAPI scrape acceptance:** require `up{job="fastapi_sample"} == 1` and queryable `fastapi_requests_total`/latency metrics after the merged scrape configuration is actually deployed to the Prometheus runtime.
- [ ] **Grafana observability correlation:** after the native → Compose Grafana migration is accepted, expose Sentry errors, Prometheus/Mimir metrics, Tempo traces, Pyroscope profiles and Loki logs as separate evidence planes, then add Grafana links from traces to profiles using stable service labels and from traces to logs using `trace_id`/`span_id` where available.
- [ ] **Alloy / Loki / Tempo pipeline:** Alloy should collect/forward FastAPI logs to Loki and OTLP traces to Tempo; do not treat Loki as a trace store. Standardize `service_name`/`service.name`, environment, release, route, `trace_id` and `span_id` labels/fields across FastAPI telemetry without introducing unbounded Prometheus label cardinality.
- [ ] **Cross-signal smoke:** extend runtime validation so one controlled FastAPI request can be correlated across Sentry event/trace, Prometheus request metrics, Loki log record, Tempo trace/span and Pyroscope profile evidence; keep every backend independently diagnosable and report partial telemetry as warning/degraded observability rather than application DOWN.
- [ ] Keep Cloudflare API uncertainty warning-only when global status cannot be confirmed.
- [ ] Continue least-privilege `fastapi_observer` A/B validation.
- [ ] Keep expensive fan-out probes bounded, cached and staggered.
- [ ] Prefer Prometheus runtime evidence where metrics exist while retaining TrueNAS App state and direct HTTP/HTTPS/TCP probes independently.

## P4 — identity and policy

- [ ] Keycloak/GitHub SSO after network/storage stability.
- [ ] Vault/OpenBao human authentication after infrastructure secrets.
- [ ] Continue NIST CSF 2.0 mapping.
- [ ] Move normal Kubernetes workloads toward Restricted Pod Security; retain explicit privileged exceptions only for required infrastructure.

## P5 — bounded post-reboot cleanup

- [ ] Archive reboot manifest, boot IDs, source SHA, operator acceptance exceptions and incident evidence.
- [ ] Confirm no disposable CSI namespace/PVC/PV/VolumeAttachment/share/dataset remains.
- [ ] Inventory legacy Docker `172.16.x.0/24` networks with owner/endpoint evidence; never use `docker network prune`.
- [ ] Protect `intranet`, `traefik_network`, `sample-observer`, `nabla-security` and `secrets-backend`.
- [ ] Remove only reviewed zero-endpoint stale networks through canonical owner lifecycle.
- [ ] Keep pre-existing CRASHED/DEPLOYING/STOPPED deferred Apps as separately tracked debt, not reboot regressions.
- [ ] Re-run orphan-shim diagnostics after Apps settle.

## Accepted code/debt reduction plan

Already accepted: agent-first local gate, deterministic autofix convergence,
generated-contract checks and the first shared TrueNAS/Docker primitives.

Remaining reduction:

1. [ ] Continue centralizing bounded TrueNAS middleware/readiness helpers in
   `scripts/lib/truenas.sh`.
2. [ ] Expand `scripts/lib/docker.sh` with shared container state/health/PID
   and Compose-project correlation.
3. [ ] Centralize compact/full output, counters and exit codes in
   `scripts/lib/diagnostic.sh`.
4. [ ] Centralize bounded HTTP/HTTPS/TCP/DNS retry semantics in
   `scripts/lib/probe.sh`.
5. [ ] Prefer canonical data/metadata over repeated Bash policy.
6. [ ] Move code-server packages/extensions into an immutable derived image.
7. [ ] Keep roadmap concise: roadmap=status/next action; runbooks=procedure;
   incidents=evidence.
8. [ ] Add an anti-duplication gate for migrated runtime primitives.

## Target operator-script architecture

```text
scripts/
├── lib/
│   ├── common.sh
│   ├── diagnostic.sh
│   ├── truenas.sh
│   ├── docker.sh
│   ├── probe.sh
│   └── secrets.sh
├── truenas/
│   ├── reboot-homelab.sh
│   ├── reconcile-reboot-resume.sh
│   ├── diagnose-platform.sh
│   └── ...
└── talos/
```

Quality gates must cover shebang/executable mode, `bash -n`, ShellCheck, contract tests and duplicate runtime primitives. Existing operator paths remain wrappers for at least one release cycle.

## Ordering rule

```text
TrueNAS storage + runtime secret normalization (preview -> stage -> per-service validate/finalize)
  -> service intent/status + initialization-control-plane refactor (P0.4)
  -> Vaultwarden migration waves for active services only (P0.5)
  -> Cyberbro free-engine baseline + provider-account onboarding / Vaultwarden edge-TLS debt
  -> Grafana native -> Compose migration (:30037 + preserved /mnt/cpool/grafana/data)
  -> Prometheus canonical DB target reconciliation (PostgreSQL, Redis, ClickHouse, InfluxDB, OpenSearch + pfSense HAProxy exporter; no Sybase)
  -> Mimir / Loki / Tempo / Alloy reconciliation
  -> FastAPI observability correlation (Sentry + Prometheus/Grafana + Alloy/Loki/Tempo + Pyroscope)
  -> Suricata EVE downstream consumption
  -> pfSense NetFlow -> Cloudflare Flow Analytics
  -> Uptime Kuma Compose :31050 + AutoKuma reconciliation
  -> deferred nginx-proxy-manager/OpenArchiver/Paperless debt
  -> bounded P5 cleanup
  -> lifecycle/topology + script-debt consolidation
  -> direct catalog standardization (v1 -> Backstage + CycloneDX; migrate desired exposure intent, then delete flat service/exposure inventory)
  -> FastAPI provider-derived resource views + Kubernetes-style conditions + Site Alban entity-ref reader
  -> CSI hardening postconditions/PSS
  -> infrastructure secrets
  -> Vault / Falco / Kubara
  -> security tooling secret materialization + shared PostgreSQL bootstrap
  -> persistent security Apps acceptance (Plumber + NetBox + Dependency-Track + DefectDojo + Neo4j)
  -> controlled reboot/resume health acceptance for the new Apps
  -> security inventory baseline (NetBox + Dependency-Track + DefectDojo + OpenSSF Scorecard)
  -> Dependency-Check SCA feed into the findings workflow; bounded ArcherySec + Faraday Community PoCs with an explicit keep/complement/drop decision before any always-on deployment
  -> Cartography + Neo4j attack-graph PoC after asset identities and provenance are stable
  -> Kubernetes ingress + test.int.albandrieu.com
  -> Karmada multi-cluster foundation (always-on TrueNAS management plane -> nabla-talos -> intermittent workstation GPU -> future cloud GPU)
  -> Scrutiny / remaining service work
  -> OpenWebUI backup/PRA acceptance (LAN UI + LiteLLM + OpenRAG + GPU, RTO P1D/RPO P1D, 3-day escalation, DMTP P7D)
  -> Docling / OpenRAG-LiteLLM with reviewed GPU placement/fallback
```


## Catalog v2 — remaining cutover

Accepted: the target authority split is defined and representative Backstage /
Compose pilots exist. This section contains only the remaining cross-repository
cutover work; detailed design stays in
[`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md)
and [`service-catalog-security-graph.md`](./service-catalog-security-graph.md).

- [ ] Generate/version `catalog/generated/entities.json` plus provenance/read
  models required by consumers.
- [ ] Put the generator behind the local quality gate in `--check` mode after
  generated output is deterministic.
- [ ] Add the minimal Nabla-only `operations.json` projection.
- [ ] Add the Cartography `nabla` import and correlate stable entity refs.
- [ ] Enrich the graph from Kubernetes, GitHub, Cloudflare and Trivy only after
  canonical identities are stable.
- [ ] Introduce OSCAL after the graph/control mapping stabilizes.
- [ ] Migrate FastAPI to the new read model, perform the coordinated one-shot
  cutover, then remove legacy compatibility contracts.
