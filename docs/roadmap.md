# Homelab roadmap

Last updated: 2026-09-20.

This file is the concise operational index. Detailed design, incident evidence and rollback procedures stay in the specialized documents:

- [Homelab ordered reboot runbook](./homelab-reboot-runbook.md)
- [TrueNAS reboot incident · 2026-09-11](./truenas-reboot-incident-20260911.md)
- [Sentry Taskbroker / Relay project-config incident · 2026-09-11](./sentry-taskbroker-project-config-incident-20260911.md)
- [Functional observability exporters](./observability-exporters.md)
- [TrueNAS CSI orphan datasets](./truenas-csi-orphan-datasets.md)
- [TrueNAS Docker IPAM roadmap](./truenas-docker-ipam-roadmap.md)
- [TrueNAS application storage and runtime env layout](./truenas-runtime-layout.md)
- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [Cyberbro provider onboarding](./cyberbro-provider-onboarding.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)
- [Kubernetes platform tools · Vault, Falco and Kubara](./kubernetes-platform-tools.md)
- [TrueNAS LXC GitHub Actions runner](./github-actions-runner-lxc.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)
- [Security tooling runtime bootstrap](./security-tooling-runtime-bootstrap.md)
- [Service catalog, security graph and SBOM architecture](./service-catalog-security-graph.md)
- [TrueNAS cron + Doco-CD deployment automation](./truenas-deployment-automation.md)

## Current platform state

- [x] Talos `v1.13.9` / Kubernetes `v1.36.3`: control plane `172.17.0.50`, workers `172.17.0.51` / `172.17.0.52`, all Ready after reboot.
- [x] Talos VM policy: `autostart=true`, graceful shutdown timeout `180s`.
- [x] TrueNAS Docker IPAM persisted after reboot: `10.200.0.0/16`, `/24` allocations, `br0=172.17.0.24/24`, protected `sample-observer=10.254.255.0/28` intact.
- [x] TrueNAS controlled reboot completed; boot ID changed and `system.ready` / Docker / VM autostart / Kubernetes readiness postconditions passed.
- [x] TrueNAS CSI controller publish path is green: `attachRequired=true`, csi-attacher, VolumeAttachment RBAC and NFS publishContext.
- [x] Fresh post-reboot TrueNAS CSI RWX acceptance is green: dynamic PVC/PV, publishContext, cross-worker write/read, namespace cleanup and Kubernetes PV reclaim.
- [x] Historical CSI dataset `cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530` was removed with supported middleware deletion after complete quiesce; no forced ZFS destroy.
- [x] Pi-hole ghost runtime and guarded exact-shim recovery are documented and covered by `diagnose-docker-orphan-shims.sh`.
- [x] Immutable reboot bundles are staged, syntax/checksum validated and atomically activated.
- [x] PR #191 introduced a manifest-aware, idempotent reboot resume reconciler and started operator-script consolidation.
- [x] Controlled reboot/resume accepted by operator. The frozen historical manifest still reports `nginx-proxy-manager=DEPLOYING`, `openarchiver=STOPPED` and `paperless-ngx=DEPLOYING`; these three are explicitly deferred service debt and are non-blocking for this reboot acceptance. Keep strict `--verify` semantics unchanged for forensic visibility.
- [x] Langfuse post-reboot web/database + worker runtime is green; OpenRAG core is green.
- [x] **Security inventory/tooling declarations:** PR #207 merged repository-managed Compose/catalog topology for Plumber, NetBox, Dependency-Track, DefectDojo, Neo4j, Cartography and OpenSSF Scorecard. Runtime acceptance remains separate from declaration acceptance.
- [x] **Catalog/security-graph target architecture:** Backstage is the generated interoperable service-catalog projection, CycloneDX is the SBOM/supply-chain projection, and Cartography/Neo4j is the analytical graph layer. `x-nabla` remains the Git authority; the existing v1 catalog remains a compatibility contract during direct migration. See `docs/service-catalog-security-graph.md`.
- [ ] **Security tooling runtime acceptance:** PR #208 merged the Vaultwarden-backed runtime files, shared PostgreSQL bootstrap, TrueNAS Custom App reconciliation, container-stability and HTTP-readiness automation. Operator execution on TrueNAS is still required before Plumber, NetBox, Dependency-Track, DefectDojo and Neo4j are considered deployed; Cartography and Scorecard remain explicit manual jobs.
- [ ] **Docling / OpenRAG ingest:** repository-managed `apps/docling/compose.yml` is prepared; runtime deployment, one bounded conversion and OpenRAG ingest/retrieve acceptance remain to be completed.
- [x] **Sentry ingestion incident resolved:** Taskbroker is stable (`running`, `restarts=0`, `exit=0`), effective StatsD defaults to resolvable `127.0.0.1:8126`, Taskworker reaches `taskbroker:50051`, Kafka group `taskworker` has an active member with lag `1`, SQLite is processing `sentry` activations, `diagnose-sentry.sh --check` reports `ok=8 failed=0 warnings=0`, and `smoke-sentry-event.sh` proves `edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse` with the synthetic event queryable in ClickHouse. Keep functional dependency/Kafka/E2E checks as the acceptance contract; see the resolved incident post-mortem.
- [ ] **FastAPI Sentry tracing acceptance:** project `2` error ingestion is proven with `/sentry-debug`: issue/group `3`, event `6c390ee8fdeb4e2b988cf316211200bd`, environment `homelab` and trace `9eab69ab62e7f50f3e3f9701ccdb95fe` are persisted in `errors_local`. The same trace currently has no row in `eap_spans_local` or `transactions_local`, so Sentry error correlation is green but FastAPI transaction/span ingestion is not yet accepted.
- [x] **Exporter conflict preflight:** TrueNAS Netdata is active; the only configured Reporting Exporter is disabled Graphite to `172.17.0.57:2003`; host ports/listeners `8125`, `9125`, `9102`, `9308` are free and no Docker publisher conflicts were found. StatsD remains deferred; Kafka exporter remains a separate controlled Kafka App lifecycle change.
- [ ] **Grafana native → Compose migration:** preserve and inspect `/mnt/cpool/grafana/data` before removing the native TrueNAS Grafana App, then recreate repository-owned Grafana on `:30037` using the same data directory. Mimir/Loki/Tempo/Alloy reconciliation is intentionally sequenced after Grafana data/dashboard/datasource acceptance.
- [ ] **Prometheus target debt:** canonical database telemetry is PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch; Sybase is intentionally excluded. Remaining DOWN targets must be diagnosed from runtime evidence. HAProxy `:9101` is the pfSense HAProxy exporter and must source pfSense statistics through `PFSENSE_HAPROXY_SCRAPE_URI`. Alloy/Mimir/Loki/Tempo are not blockers until the Grafana native → Compose migration is accepted.
- [x] **Suricata engine/rules:** the `eth0` crash loop is fixed, Suricata captures on TrueNAS `br0`, `/var/lib/suricata/rules/suricata.rules` is populated, 52k+ rules are loaded and `eve.json` is actively produced.
- [ ] **Suricata downstream consumption:** prove CrowdSec/Alloy/central observability consumes the current `eve.json` stream and keep rule refresh bounded/observable.
- [ ] **pfSense NetFlow → Cloudflare Network Analytics:** flow data no longer appears in Cloudflare Flow Analytics. Re-establish exporter/collector path, prove packet/flow emission from pfSense and confirm fresh flows arrive in Cloudflare before closing.
- [ ] **Uptime Kuma / AutoKuma:** the former native TrueNAS Uptime Kuma App has been removed and nothing listens on `172.17.0.24:31050`. AutoKuma remains stopped until a repository-owned Uptime Kuma Compose service exists.
- [x] **TrueNAS storage/runtime architecture:** repository-owned data, tracked Compose/config and runtime secret materialization are now separate contracts; `cpool/secrets` is the planned `GENERIC` root-only security dataset and application-owned datasets use the `APPS` preset when local persistence is real.
- [ ] **TrueNAS runtime env migration:** baseline inventory found 52 env materializations requiring migration work, 23 application datasets with Apps-preset drift and eight empty unowned direct-child dataset candidates. Stage canonical copies first; do not bulk-finalize env paths or recreate non-empty datasets.
- [x] **Cyberbro secret contract:** Vaultwarden item `nabla/prod/cyberbro` exists in the personal `TrueNAS` folder and renders 27 optional mappings as a `0600` env file. Provider credentials are intentionally empty until account/API onboarding is completed; empty optional providers do not block the free-engine baseline.
- [ ] **Vaultwarden edge/TLS debt:** operator evidence on 2026-09-20 shows the official `bw 2026.9.0` client receives HTTP 404 while discovering the public `https://vaultwarden.albandrieu.com/api` service. Keep the canonical public hostname, but use the new loopback client configuration on TrueNAS only after `http://127.0.0.1:30032/api/config` proves the native Vaultwarden API is healthy. Separately repair the Cloudflare Tunnel/reverse-proxy path so public `/api/config` reaches Vaultwarden, investigate the earlier transient `502 origin_bad_gateway`, and correct the icon-fetch certificate-name mismatch. Do not weaken TLS verification and do not route new automation through the legacy REST adapter.
- [ ] TrueNAS LXC GitHub Actions runner remains planned/dormant; prefer an unprivileged Ubuntu 24.04 LTS LXC plus remote builder for trusted workloads.

## P0 — controlled TrueNAS reboot accepted

The 2026-09-11 transaction is operationally accepted. Strict historical-manifest verification remains intentionally capable of reporting deferred Apps that were RUNNING before the reboot but were explicitly accepted as non-blocking afterwards.

1. [x] Preserve/restore the original persistent prepare manifest after the accidental second prepare.
2. [x] Reach the prepare boundary: all TrueNAS Apps stopped, Docker empty, Talos workers then control plane stopped, VMs `STOPPED`, `phase=PREPARED`.
3. [x] Remove the historical CSI orphan after quiesce and verify the dataset is absent.
4. [x] Reboot TrueNAS through the supported TrueNAS path; boot ID changed.
5. [x] Run `--post-reboot-check`: TrueNAS ready, Docker/IPAM/br0/observer network valid, Talos APIs reachable and Kubernetes 3/3 Ready.
6. [x] Run one fresh post-reboot CSI regression: provisioning, publishContext, cross-worker RWX and reclaim are green.
7. [x] Resume the saved original manifest sufficiently for platform acceptance. All critical services needed for the accepted baseline are RUNNING; `nginx-proxy-manager`, `openarchiver` and `paperless-ngx` are explicitly deferred and do not block this transaction.
8. [x] Diagnose the Graylog failure: logs proved `UnknownHostException: mongo` followed by connection refusal; `apps/graylog/compose.yml` requires Mongo and OpenSearch Security before `/docker-entrypoint.sh`.
9. [x] Validate the repaired #191 lifecycle planner: Docker Socket Proxy is isolated in bootstrap-runtime; foundation, primary-data, secondary-data, platform and application waves are ordered correctly; Talos/Kubernetes preflight is green.
10. [x] Close the reboot transaction operationally and move the three deferred App failures into P3 service debt. Keep the frozen manifest and strict verifier as incident evidence.

## P0.1 — reboot lifecycle hardening

- [x] Normalize TrueNAS `system.ready` representation.
- [x] Persist `PREPARING` / `PREPARED`; support `--continue-prepare`; refuse a second same-boot transaction.
- [x] Validate immutable manifest/bundle identity and checksums.
- [x] Add targeted Docker/containerd orphan-shim diagnostics/recovery.
- [x] Add `scripts/truenas/reconcile-reboot-resume.sh`: idempotent resume, separate middleware/job/readiness timeouts, per-App overrides, bounded runtime/log diagnostics and wave-level error aggregation.
- [x] Make `reboot-homelab.sh --resume` delegate App lifecycle handling to the reconciler instead of maintaining a second start/wait loop.
- [x] Re-derive ordering from the original `apps-before.json` while freezing the original selected App membership; preserve the forensic `resume-plan.json` unchanged.
- [x] Infer TrueNAS App ownership from explicit `runtime.appId`, then `apps/<app>/...` source ownership, then unique normalized service identity.
- [x] Add declarative lifecycle metadata and fixtures proving Docker Socket Proxy precedes foundation services, foundations precede data tiers, Mongo/OpenSearch precedes Graylog, PostgreSQL precedes n8n, and stop order is the exact reverse.
- [x] Add an explicit operator-acceptance/deferred annotation for historical manifests: `--accept-deferred` writes one immutable `operator-acceptance.json`, only for Apps in frozen `resume-apps.txt`, fingerprints the frozen manifest and leaves strict `--verify` semantics unchanged.
- [x] Add a fixture that simulates an interrupted prepare after earlier Apps were stopped: it proves a fresh runtime snapshot would shrink resume membership while `--continue-prepare` neither re-queries Apps nor regenerates frozen plans.
- [x] Add a Docker ghost-shim fixture and shared fail-closed guard: recovery is eligible only for `Running=true`/`Restarting=true`, `Pid=0` and exactly one matching shim; live `Pid>0`, ambiguous shim counts and non-ghost states are refused.
- [ ] Continue reducing the `no topology mapping` set; use explicit `runtime.appId` only where source ownership is ambiguous or differs from the TrueNAS App ID.
- [x] Add a generic runtime health barrier for reboot resume: a wave now requires TrueNAS `RUNNING` plus stable containers before dependent waves advance. Running containers with no Docker healthcheck remain acceptable; explicit `healthy` is required when a healthcheck exists; successful one-shot initializers may remain `Exited(0)`.
- [x] Separate lifecycle ordering from boot criticality with optional `x-nabla.lifecycle.blocksLaterWaves` (default `true`). Vaultwarden declares `false`: its recovery failure remains strict acceptance debt but cannot prevent unrelated PostgreSQL/Redis/application waves from resuming from persistent runtime materializations.
- [ ] Move service-specific readiness policy into declarative lifecycle metadata so selected backends can additionally require HTTP/TCP/application-level probes rather than only generic container stability.
- [ ] Keep current + previous known-good reboot bundles until another normal reboot cycle passes.

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

This is now a gate before further broad service migration. `docs/truenas-runtime-layout.md` is the architecture source of truth.

1. [x] Separate tracked `apps/<service>` code/config, application-owned `/mnt/cpool/<service>` data and root-only `/mnt/cpool/secrets` runtime materializations.
2. [x] Make storage discovery depend on active application bind mounts instead of arbitrary `/mnt/cpool/...` strings or Code Server workspace references.
3. [x] Define missing application datasets as TrueNAS `APPS`; keep shared/security host datasets (`compose`, `logs`, `model`, `secrets`) `GENERIC`.
4. [x] Add read-only reporting for empty datasets, Apps-preset property drift and empty unowned direct-child candidates; never auto-delete/recreate an existing dataset.
5. [x] Add canonical runtime env discovery across explicit `env_file`, repository-local ignored `.env*` and legacy `/mnt/cpool/<service>/.env*` files.
6. [x] Split migration into read-only preview, non-destructive canonical staging, per-service validation and explicit per-service finalization.
7. [x] Create/stage `cpool/secrets` as `GENERIC`, `root:root 0700`, with runtime files `root:root 0600`; the bootstrap is non-destructive and preserves legacy paths during staging.
8. [x] Resolve source collisions before staging. Differing sources fail closed, and project interpolation `.env` is represented as `.env.compose` so it cannot overwrite a service `env_file` named `.env`.
9. [x] Fix declarations with no recoverable source instead of creating empty files. Home Assistant's unused `env_file: .env` declaration was removed rather than inventing an empty runtime file.
10. [ ] **Operator acceptance pending:** `accept-runtime-env-first-wave.sh` now enforces `check -> stage -> dependency bootstrap -> deploy -> container/functional health -> finalize` one service at a time for Scanopy, Joplin and AutoKuma. Operator evidence on 2026-09-20 confirms Scanopy's canonical `.env.secrets` and Joplin's legacy `.env.secrets` are zero-key/empty placeholders, so there is no historical value to migrate; their first real credentials must be created once in Vaultwarden and then materialized canonically. AutoKuma additionally requires Uptime Kuma to be restored and RUNNING.
11. [ ] Convert remaining explicit legacy `env_file: /mnt/cpool/<service>/.env*` declarations to `/mnt/cpool/secrets/runtime/<service>/...`; remove each compatibility path only after restart/reboot acceptance.
12. [ ] Classify repository-local ignored project `.env` files: move secrets to Vaultwarden/runtime materialization, move non-secret settings to tracked defaults/config, and eliminate implicit project env dependencies where practical.
13. [ ] Review the 23 existing Apps-preset drifts. Never recreate non-empty datasets merely to change preset; separately review empty owned candidates for recreation and empty unowned candidates for deletion.
14. [x] Keep `cpool/drawio` and `cpool/litellm` as review candidates only; current Compose does not demonstrate application-owned local persistence for either service, and storage discovery does not create datasets from workspace-only references.
15. [ ] Continue metadata-only inventory in `config/secrets/manifest.json`, but defer broad Vaultwarden import/materialization until the P0.4 initialization-control-plane refactor below is accepted. Planned services may keep future metadata without becoming migration targets; disabled services must not be migrated merely because their code remains in Git.
16. [x] Maintain agent-skill rules and a CI non-regression contract so new services cannot introduce unreviewed legacy `env_file` ownership outside `/mnt/cpool/secrets/runtime/<service>/`; existing legacy services remain explicit migration debt.
17. [x] Harden the Vaultwarden renderer for workstation handoff: preserve permissions on existing parents such as `/tmp`, keep newly-created secret directories `0700`, render files `0600`, keep `BW_SESSION` unprivileged, and refuse Git-trackable output paths inside a worktree.

## P0.4 — service intent + initialization control plane

Complete this refactor **before broad secret migration**. The objective is one
declarative/idempotent initialization model rather than another per-service shell
script.

1. [x] Add optional `x-nabla.status = active|planned|disabled` with fallback `active`; keep observed runtime health separate from declared intent.
2. [x] Mark Akvorado, CrowdSec, Keycloak and n8n `planned`; mark 1Password Connect `disabled` while retaining its code. Vaultwarden is the secrets target.
3. [x] Make the TrueNAS initialization audit distinguish planned/disabled services from missing active services and suppress normal deployment recommendations for them.
4. [x] Make reboot lifecycle planning suppress planned/disabled Apps by default; explicit operator inclusion remains the bounded override.
5. [x] Add the repository-wide static secret-consumer/debt ratchet and the unprivileged Vaultwarden render -> bounded root install boundary from #210. Root must never receive `BW_SESSION`.
6. [x] Establish the generic host-local Python operations foundation: `scripts/nabla_ops/` owns the shared service-intent/state model and catalog aggregation, while `scripts/nabla-service.py` is a thin read-only CLI. Missing status keeps the `active` fallback; planned/disabled/manual services are excluded from normal initialization. Continue moving duplicated per-service logic behind this library through compatibility wrappers before broad Vaultwarden migration.
7. [x] Reuse the existing TrueNAS `apps/sample` / `fastapi-sample` runtime as the future **Nabla Service** API/UI/MCP facade instead of creating another always-on daemon or repository. Keep its stable catalog id and image identity; “Nabla Service” is a capability/profile, not a rename.
8. [ ] Add a local-controller profile to FastAPI Sample only after MCP/ops authentication and route exposure fail closed. The current `sample.albandrieu.com` Cloudflare Access ingress means privileged mutation routes must not be added until public-path denial/route non-registration is proven. FastAPI Cloud stays read-only.
9. [ ] Keep the existing `fastapi_observer` TrueNAS credential read-only. Any future bounded mutation adapter must use a separate least-privilege execution identity and must never expose generic shell/`midclt` passthrough.
10. [ ] Extend declarative `x-nabla` metadata with secret-contract, initialization/dependency and readiness policy where it removes duplicated script knowledge; generate machine-readable initialization contracts rather than manually maintaining parallel inventories. Implement generic handlers (TrueNAS App reconcile, PostgreSQL role/database, HTTP/TCP readiness, manual jobs) in `nabla_ops` before migrating additional secret waves.
11. [ ] Add durable value-blind service state (`DECLARED -> SECRETS_DECLARED -> SECRETS_MATERIALIZED -> DEPENDENCIES_READY -> DEPLOYED -> RUNTIME_ACCEPTED -> REBOOT_ACCEPTED`) plus `flock`/transaction boundaries and idempotent bounded retries. The stage enum now lives in `nabla_ops`; persistence/mutation remains deliberately deferred until transaction semantics are implemented.
12. [x] Add a root-readable, value-blind filesystem inventory for `.env` / `.env.secrets` migration candidates; it reports paths/metadata only and complements the canonical migration planner.
13. [x] Stage `sample` as the first path-normalization pilot without Vaultwarden. Operator evidence on 2026-09-19 confirms `/mnt/cpool/secrets/runtime/sample/.env` and `.env.secrets` are root:root `0600`, non-empty and byte-consistent with the legacy sources; legacy files remain intact.
14. [ ] **Finish Sample before deleting legacy dotenvs:** restage after the local `.env` cleanup, redeploy from the canonical paths, require `/health`, version, dedicated observer-network and TrueNAS read-only observer acceptance, then perform one controlled reboot acceptance. Only then run `--finalize sample`; after an additional clean observation/reboot cycle, remove the compatibility symlinks once repository/runtime consumers no longer reference `/mnt/cpool/sample/.env*`.
15. [ ] Normalize Sample database ownership: TrueNAS staging depends on shared PostgreSQL at `172.17.0.24:5432`; create database **`sample`** owned by dedicated LOGIN role **`sample`** (no SUPERUSER/CREATEDB/CREATEROLE/REPLICATION), bootstrap it idempotently with `scripts/truenas/bootstrap-sample-postgres.sh --check|--apply`, render its password through the canonical Sample secret flow, and require an authentication/application smoke before cutover. Target local config is `POSTGRES_HOST=172.17.0.24`, `POSTGRES_PORT=5432`, `POSTGRES_DB=sample`, `POSTGRES_USER=sample`. Move the historical Supabase pooler identity to explicit `SUPABASE_*` variables in `fastapi-sample`; never reuse the `postgres` superuser for Sample.
16. [ ] Resolve the Scrutiny source conflict value-blind: repository-local `apps/scrutiny/.env.secrets` and `/mnt/cpool/scrutiny/.env.secrets` differ and must not be auto-merged. Compare key sets/value equality by key name only, select the runtime-authoritative source with evidence, then restage.
17. [ ] Initialize the currently missing declared datasets only with their service rollout: `cyberbro`, `defectdojo`, `dependency-track`, `neo4j`, `netbox`. Their absence remains expected preparation debt until deployment; do not create them merely to make the global check green.
18. [ ] Add deterministic local tests for status fallback, secret privilege boundaries, initialization state transitions and generated contracts so routine agent work does not require GitHub Actions as the feedback loop.
19. [x] Bound TrueNAS deployment automation: cron job `id=6` (`albandrieu`, hourly at minute 0) only fast-forward synchronizes the local `master` checkout, refuses destructive resets/non-fast-forwards, ignores dirty submodule worktrees, and becomes a no-op on feature branches. It no longer starts/replaces Doco-CD; the running Doco-CD independently polls reviewed remote `master`. `sample` remains explicitly owned by its TrueNAS Custom App update helper during the canonical-path pilot.
20. [x] Provide user-space TrueNAS development tooling bootstrap with mise/uv plus an isolated venv containing pre-commit/pytest/PyYAML, without enabling appliance `apt` package management. The agent gate auto-prepends `$HOME/.cache/nabla-compose/dev-venv/bin` when present; `bootstrap-dev-tools.sh --persist-shell-path` can idempotently add the venv and `~/.local/bin` to the operator `.bashrc`. Keep this separate from the existing root-managed `/mnt/cpool/tools/bin/{kubectl,talosctl}` operator-tool contract.
21. [x] Add a pinned/checksummed user-space Bitwarden Password Manager CLI bootstrap for TrueNAS (`~/.local/bin/bw`, current pin `2026.9.0`) so Vaultwarden migration does not depend on system packages, Node/npm or the repository mise graph.
22. [x] Identify Doco-CD runtime ownership from live labels: TrueNAS uses `docker-compose-truenas.yml`; the workstation separately uses `docker-compose.yml` + `docker-compose.override.yml`. Mark root `docker-compose.yml` workstation-only. Correct the TrueNAS poll targets to `apps/vaultwarden/compose.yml` and `apps/garage/compose.yml`, pin Doco-CD `0.85.1`, retain webhook secret-provider mode, and keep Sample outside Doco-CD.
23. [ ] Reconcile the **live** TrueNAS Doco-CD container after #211 is accepted: verify required runtime env/secret-store inputs without printing values, apply only `docker-compose-truenas.yml`, then copy/read `/poll-config.yml` back from the container and prove `reference: master`, interval `3600`, and canonical Vaultwarden/Garage paths. Do not start `bootstrap/compose.yaml` alongside it.
24. [ ] Retire the inactive 1Password bootstrap dependency deliberately: `bootstrap/compose.yaml` remains historical/recovery code but must stay outside automatic cron execution while 1Password is `disabled`. Migrate any still-needed Doco-CD external-secret mappings to the Vaultwarden/webhook path before deleting 1Password recovery material.

Exit gate: broad Vaultwarden migration starts only when the generic host-local
control path can audit/plan one service, preserve status intent, execute
idempotently and report acceptance without exposing values. Normal reboot must
consume already-materialized root-only runtime files and remain independent from
Vaultwarden availability. FastAPI Sample may expose plans/state and later bounded
local operations, but it is not part of the minimum boot dependency chain.

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

Treat `x-nabla` plus the generated `catalog/services.json` / `catalog/service-topology.json` as the authoritative application/service catalog. Add specialized tools as domain-specific consumers or enrichment sources rather than introducing competing inventories.

Standardization/migration contract: see `docs/service-catalog-security-graph.md`.

- [ ] **Direct v1 -> Backstage projection:** generate Backstage Component/Resource/API/System/Domain entities from the existing generated catalog. Do not hand-rewrite services and do not deploy Backstage as a prerequisite.
- [ ] **CycloneDX projection:** generate an aggregate service/component BOM from the same IDs and attach Trivy per-image/per-source SBOMs by stable service ID, image digest and pURL.
- [ ] **Cross-projection quality gate:** require one `catalogRevision`, resolvable IDs/relations, no secret export, and deterministic parity between legacy JSON, Backstage and CycloneDX artifacts.
- [ ] **FastAPI Sample migration:** add a v2 read-only Backstage-shaped catalog/topology adapter keyed by stable service ID; keep current v1 inventory/exposure files only as compatibility and policy-exception overlays during the transition.
- [ ] **Site Alban migration:** prefer the FastAPI v2 entities/topology and keep the current bundled v1 catalog only as a last-known-good fallback until revision-parity tests are green.
- [ ] **Cartography correlation:** load Nabla identities/typed relations into Neo4j with provenance/freshness, then correlate provider/runtime observations. Inferred graph edges remain analytical and must never silently alter lifecycle ordering.
- [ ] **Security evidence flow:** prove one representative `Trivy -> CycloneDX -> Dependency-Track` path, one scanner/Trivy import into DefectDojo, and one bounded Neo4j/Cartography rule joining service identity to exposure/vulnerability evidence.
- [ ] Normalize `securityFunctions` to NIST CSF 2.0 `Govern | Identify | Protect | Detect | Respond | Recover` as classification metadata, not as a risk score.

Runtime preparation contract for this wave:

1. `scripts/truenas/prepare-security-tooling-secrets.sh --apply <app|all>` renders the exact Vaultwarden item into `/mnt/cpool/secrets/runtime/<service>/.env.secrets` as `root:root 0600`.
2. `--verify-vaultwarden` proves byte-for-byte parity between the unlocked Vaultwarden item and the runtime materialization without printing values.
3. `scripts/truenas/bootstrap-security-tooling-postgres.sh --apply <app>` idempotently creates/rotates dedicated shared-PostgreSQL roles and databases for Plumber, NetBox, Dependency-Track and DefectDojo, then proves authentication.
4. `scripts/truenas/deploy-security-tooling.sh --apply <app|all>` validates Compose/catalog contracts, storage, database prerequisites, reconciles the TrueNAS Custom App, waits for middleware `RUNNING`, validates container stability and probes the service HTTP endpoint.
5. Cartography and Scorecard remain `profile: manual` jobs: validate their Compose/secrets but do not register them as always-on TrueNAS Apps or reboot obligations.
6. After runtime acceptance, execute one controlled reboot and require the topology-derived resume waves plus the generic container health barrier to pass before marking this wave stable.


- [ ] **NetBox** — Compose/catalog and runtime bootstrap are prepared; deploy and accept [netbox-community/netbox](https://github.com/netbox-community/netbox) for network/infrastructure source-of-truth use cases: IPAM, VLANs, prefixes, devices/VMs, interfaces and infrastructure ownership. Define explicit reconciliation boundaries with `x-nabla` so NetBox owns network/infrastructure data while `x-nabla` remains authoritative for service identity and service-to-service topology.
- [ ] **OWASP DefectDojo** — Compose/catalog and runtime bootstrap are prepared; deploy [DefectDojo](https://github.com/DefectDojo/django-DefectDojo) as the normalized vulnerability/finding aggregation layer. Ingest selected SAST, SCA, secrets, IaC, container, DAST and infrastructure scanner outputs through import/reimport/API; validate deduplication and preserve scanner evidence instead of treating DefectDojo as an asset source of truth.
- [ ] **OWASP Dependency-Track** — Compose/catalog and runtime bootstrap are prepared; deploy [Dependency-Track](https://github.com/DependencyTrack/dependency-track) for CycloneDX SBOM/component inventory, software-supply-chain risk and vulnerability tracking. Start with one representative service, generate/import an SBOM, then reconcile component/project identity with the canonical Nabla service ID. Reference implementation guide: [Stéphane Robert — Dependency-Track](https://blog.stephane-robert.info/docs/securiser/analyser-code/dependency-track/).
- [ ] **OpenSSF Scorecard** — manual-job Compose and Vaultwarden contract are prepared; integrate [OpenSSF Scorecard](https://github.com/ossf/scorecard) for repository and upstream dependency security-health checks. Keep Scorecard findings as supply-chain posture evidence, not as an overall service-risk score; export relevant results into the vulnerability/security reporting path.
- [ ] **Cartography + Neo4j attack graph PoC** — Neo4j persistent-App bootstrap and Cartography manual-job secret contract are prepared; evaluate [cartography-cncf/cartography](https://github.com/cartography-cncf/cartography) backed by [Neo4j](https://neo4j.com/) only after the canonical asset/service inventory is stable. Ingest GitHub, Kubernetes, cloud/identity/security sources that exist in the environment, enrich the graph with `x-nabla` service ownership/topology where useful, and prove bounded Cypher queries for attack paths, internet exposure, privilege relationships and blast-radius analysis. Do not make Neo4j a second CMDB or use inferred graph edges to alter lifecycle ordering automatically.
- [ ] Define an interoperability contract: `x-nabla` = service/application identity + declared dependencies; NetBox = network/infrastructure intent; Dependency-Track = components/SBOM; DefectDojo = normalized security findings; Scorecard = repository/upstream security posture; Cartography/Neo4j = relationship/attack-path analysis. Reconciliation must use stable identifiers and preserve provenance/evidence.

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

1. [x] **One resume implementation.** `reboot-homelab.sh --resume` delegates App lifecycle reconciliation to `reconcile-reboot-resume.sh --apply`.
2. [ ] **`scripts/lib/truenas.sh`.** Continue centralizing bounded middleware calls, normalized readiness and reboot-manifest helpers. Shared Custom App state/reconcile/wait primitives are now used by the security-tooling deployment path; remaining legacy deploy scripts still duplicate lifecycle logic.
3. [ ] **`scripts/lib/docker.sh`.** Initial side-effect-free orphan-shim recovery guard is centralized and fixture-covered. Continue with shared container state/health/PID/restarts/exit snapshots, Compose-project selection and correlation helpers.
4. [ ] **`scripts/lib/diagnostic.sh`.** Centralize compact/full output, counters and stable exit codes.
5. [ ] **`scripts/lib/probe.sh`.** One bounded HTTP/HTTPS/TCP/DNS probe implementation with retry semantics.
6. [x] **`scripts/lib/secrets.sh`.** Initial shared owner/mode/presence, targeted dotenv extraction and Vaultwarden rendering helpers exist without printing secret values. Continue migrating legacy service-specific checks opportunistically.
7. [ ] **Data over Bash policy.** Move lifecycle/readiness policy into canonical `x-nabla`/catalog metadata.
8. [ ] **Prebuilt code-server image.** Bake packages/extensions into an immutable derived image.
9. [x] **Incident fixtures.** Interrupted prepare/continue membership drift and Docker ghost-shim eligibility/refusal are both covered by deterministic fixtures.
10. [ ] **Keep roadmap concise.** Roadmap=status/next action; runbooks=procedure; incident docs=evidence.
11. [ ] **Anti-duplication quality gate.** Reject redefinitions of migrated runtime primitives.
12. [x] **Runtime-layout non-regression gate.** CI rejects new unreviewed legacy `env_file` service ownership, verifies Home Assistant has no phantom dotenv dependency, and keeps canonical first-wave paths under `/mnt/cpool/secrets/runtime/<service>/`. Existing legacy services remain an explicit allowlisted migration set until staged/cut over.

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
  -> direct catalog standardization (v1 -> Backstage + CycloneDX projections, same catalogRevision)
  -> FastAPI v2 catalog facade + Site Alban v2 reader with v1 fallback
  -> CSI hardening postconditions/PSS
  -> infrastructure secrets
  -> Vault / Falco / Kubara
  -> security tooling secret materialization + shared PostgreSQL bootstrap
  -> persistent security Apps acceptance (Plumber + NetBox + Dependency-Track + DefectDojo + Neo4j)
  -> controlled reboot/resume health acceptance for the new Apps
  -> security inventory baseline (NetBox + Dependency-Track + DefectDojo + OpenSSF Scorecard)
  -> Cartography + Neo4j attack-graph PoC after asset identities and provenance are stable
  -> Kubernetes ingress + test.int.albandrieu.com
  -> Karmada multi-cluster foundation (always-on TrueNAS management plane -> nabla-talos -> intermittent workstation GPU -> future cloud GPU)
  -> Scrutiny / remaining service work
  -> Docling / OpenRAG-LiteLLM with reviewed GPU placement/fallback
```
