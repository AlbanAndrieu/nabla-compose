# Homelab roadmap

Last updated: 2026-10-02.

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

## Roadmap contract

This file deliberately keeps **status, ordering and acceptance boundaries**, not
step-by-step procedures. The specialized document linked by an item owns the
commands, rollback and detailed diagnostic evidence.

Completion semantics:

- **declared** means configuration/catalog/code exists; it does not mean the
  service is deployed;
- **runtime accepted** requires container/application health and a functional
  smoke appropriate to the service;
- **reboot accepted** requires the service to recover from canonical persisted
  state after a controlled reboot/restart cycle;
- security-tooling acceptance requires usable evidence/output, not merely a
  reachable UI;
- observability acceptance requires the relevant signal to be queryable, not
  merely an exporter process in RUNNING state;
- a warning caused by an optional/external dependency must remain distinguishable
  from application DOWN;
- rollback material is retained until the relevant observation/reboot gate is
  complete;
- completed historical evidence belongs in incidents/runbooks and is compacted
  here into an accepted milestone.

Current execution lanes:

1. dependency automation: finish hosted Renovate acceptance without Actions
   runner dependency;
2. recovery: close DNS/Talos maintenance acceptance and remaining CSI hardening;
3. runtime/secrets: continue staged canonical env/dataset migration one service
   at a time;
4. security platform: accept the already-declared inventory/findings tools
   before adding more always-on services;
5. observability: migrate Grafana before reconciling the full
   Mimir/Loki/Tempo/Alloy stack;
6. Kubernetes: keep Karmada/GPU federation outside the critical path until the
   single home cluster and its storage/security baseline are stable.

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
- DNS recovery guard is versioned: Talos generation pins pfSense/Unbound
  `172.17.0.1` by default and the pfSense posture audit rejects TrueNAS/Pi-hole
  `172.17.0.24` as the general LAN DHCP resolver.

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
- [ ] DNS recovery acceptance: during the next controlled maintenance cycle,
  stop Pi-hole, rerun the pfSense posture audit and Talos `ResolverStatus` /
  `DNSUpstream` checks, then prove public registry resolution still works before
  closing the 2026-09-27 incident follow-up.

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
- [x] Make `smoke-truenas-csi-nfs.sh` directly verify bounded TrueNAS middleware dataset, NFS share and ZFS resource disappearance after Kubernetes reclaim; the apply smoke now fails closed if the authoritative appliance postcondition is unavailable or does not converge.
- [x] Treat TrueNAS API/DeleteVolume success as insufficient unless middleware + ZFS postconditions are satisfied, explicitly guarding the NAS-143316 false-success class.
- [x] Keep reclaim validation independent from the CSI write credential: the smoke uses local TrueNAS `midclt`/`zfs` read-only evidence and never consumes `TRUENAS_CSI_API_KEY` for postcondition checks.
- [x] Harden smoke Pods toward Restricted PSS: non-root UID/GID + `fsGroup`, `allowPrivilegeEscalation=false`, read-only rootfs, drop `ALL` and seccomp `RuntimeDefault`; the privileged CSI driver namespace policy remains scoped separately.
- [x] Evaluate TrueNAS CSI `v1.0.3 -> v1.3.0`: v1.3.0 is a worthwhile later upgrade (session reconnect, metrics/Helm and storage fixes), but **do not bump in this PR**. The controlled reboot/DNS acceptance must be green first, and upstream v1.3.0 still calls legacy `auth.login_with_api_key`, so the bump does not close the TrueNAS 27 authentication debt.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27. Upstream TrueNAS CSI v1.3.0 still authenticates with the API key alone through that RPC method; track an upstream username/SCRAM-capable release or a deliberately reviewed client/fork rather than assuming the v1.3.0 bump fixes authentication.

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

Canonical detail lives in
[`security-inventory-tooling-roadmap.md`](./security-inventory-tooling-roadmap.md),
[`security-tooling-control-architecture.md`](./security-tooling-control-architecture.md)
and
[`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md).
The main roadmap keeps only phase gates:

- [ ] **P2.1.a — preparation:** freeze/parity-check legacy catalog input, keep
  schemas/provenance deterministic and reject duplicate ownership.
- [ ] **P2.1.b — pilot:** prove Backstage + Compose authority on representative
  services and show desired intent survives provider outages.
- [ ] **P2.1.c — bulk migration:** generate/review service descriptors, complete
  BIA/PRA requirements for business-relevant services and couple touched secret
  migrations with the same service bundle.
- [ ] **P2.1.d — consumers:** prepare FastAPI/site/operational consumers against
  the v2 read model before destructive cutover.
- [ ] **P2.1.e — one-shot cutover:** switch consumers together; do not maintain a
  long-lived v1/v2 compatibility architecture.
- [ ] **P2.1.f — cleanup/acceptance:** remove legacy contracts only after reboot,
  health, topology and consumer acceptance.
- [ ] **P2.1.g — later enrichment:** keep provider-native IaC cleanup,
  Cartography/Neo4j enrichment and OSCAL outside the critical cutover path.

Security-tooling acceptance within this workstream:

- [ ] Dependency-Check produces reproducible SCA evidence and DefectDojo remains
  the authoritative findings/remediation store.
- [ ] Evaluate ArcherySec and Faraday as bounded complementary PoCs; record
  explicit keep/complement/drop decisions and avoid competing finding databases.
- [ ] Deploy and accept an endpoint hardware/software inventory manager, with
  **OCS Inventory NG** as the default candidate. OCS owns observed endpoint
  facts only; `x-nabla` keeps application/service identity and NetBox keeps
  infrastructure intent. Detailed version, storage, enrollment and reconciliation
  gates live in `security-inventory-tooling-roadmap.md`.
- [ ] Complete NetBox/OCS Inventory/Dependency-Track/DefectDojo/Neo4j runtime
  acceptance before treating declarations as deployed services.
- [ ] Keep OpenWebUI/OpenRAG BIA/PRA evidence in
  [`openwebui-backup-pra.md`](./openwebui-backup-pra.md), not duplicated here.
- [ ] **OWASP OpenCRE standards correlation:** add a repository-owned
  `apps/opencre/compose.yml` using the official
  `ghcr.io/owasp/opencre/opencre` image, pinned to a reviewed version/digest
  before activation. Bind the upstream port `5000` internally, set
  `CRE_ENABLE_HEALTH=true` and use `GET /rest/v1/health` as the bounded
  readiness/uptime probe. Use OpenCRE to correlate Common Requirements across
  DSOMM, OWASP SAMM, NIST, CIS, ISO and other mapped standards; it is the
  reference/correlation layer, not the maturity score of record. Keep imports
  disabled by default and reuse the shared Neo4j service only after compatibility
  is proven instead of introducing an application-local graph database by
  default.
- [ ] **OWASP DSOMM assessment:** deploy the repository-owned DSOMM UI on
  `172.17.0.24:31088` while it remains `status: planned`.
  - [x] Storage contract explicitly owns `cpool/dsomm` with the Apps preset.
  - [ ] On TrueNAS, run `bootstrap-repository-storage.sh --apply dsomm` then
    `--check dsomm` and prove the dataset exists before runtime activation.
  - [ ] Preserve progress/evidence under protected TrueNAS runtime state, run the
    pinned `tweag/dsomm-baseline` job against the selected Nabla repositories,
    route repository evidence into the two default maturity contexts (`Nabla
    Platform` and `Nabla Applications`), then
    complete unsupported/manual activities with reviewed evidence. The pinned
    Tweag baseline predates DSOMM 5.0, so Agentic AI/Identity and other uncovered
    activities remain explicit human-review scope. Promote DSOMM to `active`
    only after runtime acceptance; automated baseline output is supporting
    evidence, not the maturity verdict.
- [x] Vendor the Cloudflare `security-audit-skill` and publish an initial
  source-first one-shot under `docs/security-audits/`; the 2026-10-01 run is
  explicitly partial/incomplete and is not a clean-security attestation.
- [ ] Validate committed audit JSON with the vendored Cloudflare findings and
  coverage-ledger validators through the local Pre-commit contract; keep this
  acceptance open until the focused local test is executed on a full checkout.
- [ ] Validate the Scanopy daemon bootstrap boundary from that audit by pinning
  the deployed digest, proving initialization state + TCP/60073 exposure
  passively, then either close the lead or harden bind/firewall/socket access.

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
- [ ] Baseline Docker storage debt with `audit-docker-storage-debt.sh --check`; compare image count, `overlay2` directory cardinality and `cpool/ix-apps/docker` used bytes against the 2026-10-03 baseline (764 images / 7,408 overlay2 dirs / ~525 GiB).
- [ ] Review targeted Docker cleanup only after PRA acceptance: dangling images, old unmanaged/exited containers and build cache. Never use `docker system prune` or `docker network prune` as a blanket cleanup.
- [ ] Reboot once after any reviewed cleanup and record Docker cold-start convergence duration; objective is to reduce metadata reload time without sacrificing rollback/re-pull safety.

## Accepted code/debt reduction plan

Already accepted: agent-first local gate, deterministic autofix convergence,
generated-contract checks and the first shared TrueNAS/Docker primitives.
Compose discovery is also normalized across generator/Pre-commit for dotted and
hyphenated root variants such as `docker-compose-truenas.yml`.
Pre-commit configuration parsing/unicity is now an explicit local contract so
malformed regex quoting or duplicated hook IDs fail before publication.

Remaining reduction:

1. [ ] Continue centralizing bounded TrueNAS middleware/readiness helpers in
   `scripts/lib/truenas.sh`; dataset-by-ID and NFS-share-by-path reads are now
   shared by CSI preflight/reclaim while service-specific forensic loops stay local.
2. [ ] Expand `scripts/lib/docker.sh` with shared container state/health/PID
   and Compose-project correlation.
3. [x] Centralize diagnostic output plumbing: `scripts/lib/diagnostic.sh`
   owns compact/full wrapper delegation for the 23 migrated operator scripts,
   while `scripts/run-diagnostic.sh` remains canonical for private detailed
   logs, counters, bounded summaries and exit-code propagation.
4. [ ] Centralize bounded HTTP/HTTPS/TCP/DNS retry semantics in
   `scripts/lib/probe.sh`.
5. [ ] Prefer canonical data/metadata over repeated Bash policy.
6. [ ] Move code-server packages/extensions into an immutable derived image.
7. [x] Keep roadmap concise: roadmap=status/next action; runbooks=procedure;
   incidents=evidence. Historical/duplicate planning has been consolidated while
   diagnostic, rollback and acceptance evidence remains in canonical documents.
8. [x] Add an anti-duplication gate for migrated runtime primitives. Canonical
   owners are declared in `config/quality/runtime-primitives.json`; Pre-commit
   and the agent gate now reject foreign shell definitions while full local
   validation also proves the owner definition still exists exactly once.
9. [x] Make runtime health consumers lifecycle-aware: `planned`/`disabled`
   services remain catalog-visible but no longer generate Gatus/AutoKuma health
   expectations until activation.

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
  -> security inventory baseline (NetBox + OCS Inventory + Dependency-Track + DefectDojo + OpenSSF Scorecard)
  -> Dependency-Check SCA feed into the findings workflow; bounded ArcherySec + Faraday Community PoCs with an explicit keep/complement/drop decision before any always-on deployment
  -> Cartography + Neo4j attack-graph PoC after asset identities and provenance are stable
  -> Kubernetes ingress + test.int.albandrieu.com
  -> Karmada multi-cluster foundation (always-on TrueNAS management plane -> nabla-talos -> intermittent workstation GPU -> future cloud GPU)
  -> Scrutiny / remaining service work
  -> OpenWebUI backup/PRA acceptance (LAN UI + LiteLLM + OpenRAG + GPU, RTO P1D/RPO P1D, 3-day escalation, DMTP P7D)
  -> Docling / OpenRAG-LiteLLM with reviewed GPU placement/fallback
```
