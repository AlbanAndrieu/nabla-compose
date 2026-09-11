# Homelab roadmap

Last updated: 2026-09-11.

This file is the concise operational index. Detailed design, incident evidence and rollback procedures stay in the specialized documents:

- [Homelab ordered reboot runbook](./homelab-reboot-runbook.md)
- [TrueNAS reboot incident · 2026-09-11](./truenas-reboot-incident-20260911.md)
- [Sentry Taskbroker / Relay project-config incident · 2026-09-11](./sentry-taskbroker-project-config-incident-20260911.md)
- [Functional observability exporters](./observability-exporters.md)
- [TrueNAS CSI orphan datasets](./truenas-csi-orphan-datasets.md)
- [TrueNAS Docker IPAM roadmap](./truenas-docker-ipam-roadmap.md)
- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)
- [Kubernetes platform tools · Vault, Falco and Kubara](./kubernetes-platform-tools.md)
- [TrueNAS LXC GitHub Actions runner](./github-actions-runner-lxc.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)

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
- [ ] **Docling / OpenRAG ingest:** native `docling-serve` is stopped, so OpenRAG knowledge ingestion is unavailable until Docling is restored and its ingestion path is validated.
- [ ] **Sentry ingestion incident:** original failure remains a Taskbroker Kafka consumer rejoin problem after `SESSTMOUT`, with zero active `taskworker` members and growing lag while SQLite remains empty. A targeted Taskbroker restart exposed a second, newer startup/configuration failure: the live bind-mounted metrics/StatsD address was not resolvable, causing Taskbroker to panic in `src/metrics.rs`, exit `101` and restart-loop. Restore Taskbroker bootability first, then resume Kafka rejoin diagnosis. Taskworker Docker health remained green while gRPC to `taskbroker:50051` was functionally down, so dependency reachability is now part of acceptance.
- [x] **Exporter conflict preflight:** TrueNAS Netdata is active; the only configured Reporting Exporter is disabled Graphite to `172.17.0.57:2003`; host ports/listeners `8125`, `9125`, `9102`, `9308` are free and no Docker publisher conflicts were found. StatsD remains deferred; Kafka exporter remains a separate controlled Kafka App lifecycle change.
- [ ] **Prometheus target debt:** connection-refused DOWN scrapes remain for Alloy `:12345`, HAProxy `:9101`, Loki `:3100`, Mimir `:9009`, OpenSearch `:9114`, OpenSearch Security `:9115`, postgres_exporter `:9187`, Sybase `:9113` and Tempo `:3200`. Treat each as an ownership/listener/configuration diagnosis, not automatically as a service outage. Mimir is high priority because Prometheus remote-write also targets `172.17.0.24:9009`.
- [x] **Suricata engine/rules:** the `eth0` crash loop is fixed, Suricata captures on TrueNAS `br0`, `/var/lib/suricata/rules/suricata.rules` is populated, 52k+ rules are loaded and `eve.json` is actively produced.
- [ ] **Suricata downstream consumption:** prove CrowdSec/Alloy/central observability consumes the current `eve.json` stream and keep rule refresh bounded/observable.
- [ ] **pfSense NetFlow → Cloudflare Network Analytics:** flow data no longer appears in Cloudflare Flow Analytics. Re-establish exporter/collector path, prove packet/flow emission from pfSense and confirm fresh flows arrive in Cloudflare before closing.
- [ ] **Uptime Kuma / AutoKuma:** the former native TrueNAS Uptime Kuma App has been removed and nothing listens on `172.17.0.24:31050`. AutoKuma remains stopped until a repository-owned Uptime Kuma Compose service exists.
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
- [ ] Add an explicit operator-acceptance/deferred annotation for historical manifests so an incident can record non-blocking exceptions without weakening strict verification or changing frozen membership.
- [ ] Add a fixture that simulates an interrupted prepare after earlier Apps were stopped and proves continuation never regenerates the frozen manifest/plans.
- [ ] Add a Docker fixture for `Running=true`, `Pid=0`, exactly-one-shim recovery and refusal when `Pid>0`.
- [ ] Continue reducing the `no topology mapping` set; use explicit `runtime.appId` only where source ownership is ambiguous or differs from the TrueNAS App ID.
- [ ] Add health-aware dependency acceptance metadata so a backend wave can require container/service readiness, not only TrueNAS App `RUNNING`, where a consumer cannot self-wait safely.
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

## P1 — infrastructure secrets

1. [ ] OpenTofu/Terragrunt and Garage backend credentials.
2. [ ] Dedicated TrueNAS infrastructure automation identity; never reuse the FastAPI observer identity.
3. [ ] Nexus automation credentials.
4. [ ] Talos/Kubernetes/CSI machine credentials.
5. [ ] Root-owned `0600` runtime rendering.
6. [ ] Retain encrypted recovery material.
7. [ ] Move long-lived machine secrets to Vault/OpenBao only after storage persistence and rollback are proven.

## P2 — platform/security tools

- [ ] Vault/OpenBao after CSI/reboot acceptance.
- [ ] Falco after infrastructure baseline stabilizes.
- [ ] Kubara config/bootstrap.
- [ ] Traefik/Kubara ingress with an explicit bare-metal exposure model.
- [ ] FastAPI Kubernetes smoke using an immutable image and `test.albandrieu.com` after storage and ingress ownership are stable.

## P3 — runtime/services

- [x] Prometheus, Grafana, Graylog baseline, CrowdSec resume intent, Langflow, Wazuh core and OpenRAG core exist.
- [x] Langfuse post-reboot runtime acceptance: web/database and worker checks are green.
- [ ] **Priority: restore Sentry Taskbroker bootability** — inspect the actual `/etc/taskbroker/config.yml` bind source. The targeted restart exposed a stale/unresolvable metrics destination that makes Taskbroker panic in `src/metrics.rs`, exit `101` and restart-loop. Reconcile the live file with reviewed repository config, then require stable `RUNNING`, `pid>0`, no restart growth, gRPC `:50051` listening and functional Taskworker→Taskbroker reachability.
- [ ] **Then resume Sentry Kafka rejoin diagnosis** — once Taskbroker is stable, require Kafka group `taskworker` to regain an active member and drain the backlog (observed lag grew from `53204` to `54204+` during the failed restart experiment), Relay project-config pending to clear, and `smoke-sentry-event.sh` to prove edge → Relay → Kafka → ingest → Snuba → ClickHouse. Do not reset offsets or delete SQLite.
- [x] **Exporter conflict preflight** — TrueNAS native reporting/Netdata and ports `8125/9125/9102/9308` were inventoried; no listener/publisher conflict exists. StatsD stays deferred until Sentry is functionally recovered. Kafka exporter remains with `apps/kafka` and must be deployed only in a controlled Kafka App update window.
- [ ] Track Sentry self-hosted 26.8 Kafka coordinator/session-timeout and Taskbroker consumer-rejoin behavior as upstream/version debt. Process/container health is insufficient; functional health must include Taskworker→Taskbroker reachability, active Kafka membership and end-to-end ingestion.
- [ ] **Prometheus DOWN-target reconciliation** — repair or intentionally remove stale scrapes for Alloy `:12345`, HAProxy `:9101`, Loki `:3100`, Mimir `:9009`, OpenSearch `:9114`, OpenSearch Security `:9115`, postgres_exporter `:9187`, Sybase `:9113` and Tempo `:3200`. Fix Mimir first because Prometheus remote-write also points to `172.17.0.24:9009/api/v1/push`.
- [x] **Suricata capture + rules/EVE acceptance** — engine RUNNING on TrueNAS `br0`; persistent rules file populated; ~52k rules load; alerts generated; `eve.json` active.
- [ ] **Suricata downstream consumption** — prove CrowdSec/Alloy/central observability consumes current EVE and monitor kernel drops/rule refresh health.
- [ ] **pfSense NetFlow → Cloudflare Network Analytics** — restore flow export path and prove fresh flow arrival end to end.
- [ ] Scrutiny: finish TrueNAS SMART acceptance plus workstation collector with pinned v0.9.3 collector.
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
2. [ ] **`scripts/lib/truenas.sh`.** Centralize bounded middleware calls, normalized readiness, App state, lifecycle waits and persistent reboot-manifest helpers.
3. [ ] **`scripts/lib/docker.sh`.** Centralize container state/health/PID/restarts/exit, Compose-project selection and orphan-shim correlation.
4. [ ] **`scripts/lib/diagnostic.sh`.** Centralize compact/full output, counters and stable exit codes.
5. [ ] **`scripts/lib/probe.sh`.** One bounded HTTP/HTTPS/TCP/DNS probe implementation with retry semantics.
6. [ ] **`scripts/lib/secrets.sh`.** Centralize owner/mode/presence checks without secret disclosure.
7. [ ] **Data over Bash policy.** Move lifecycle/readiness policy into canonical `x-nabla`/catalog metadata.
8. [ ] **Prebuilt code-server image.** Bake packages/extensions into an immutable derived image.
9. [ ] **Incident fixtures.** Complete interrupted prepare/continue and Docker ghost-shim fixtures.
10. [ ] **Keep roadmap concise.** Roadmap=status/next action; runbooks=procedure; incident docs=evidence.
11. [ ] **Anti-duplication quality gate.** Reject redefinitions of migrated runtime primitives.

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
restore Taskbroker bootability / gRPC
  -> Taskbroker Kafka membership + lag recovery
  -> Sentry end-to-end smoke
  -> Prometheus DOWN-target reconciliation (Mimir first)
  -> Suricata EVE downstream consumption
  -> pfSense NetFlow -> Cloudflare Flow Analytics
  -> Uptime Kuma Compose :31050 + AutoKuma reconciliation
  -> deferred nginx-proxy-manager/OpenArchiver/Paperless debt
  -> bounded P5 cleanup
  -> lifecycle/topology + script-debt consolidation
  -> CSI hardening postconditions/PSS
  -> infrastructure secrets
  -> Vault / Falco / Kubara
  -> Kubernetes ingress + test.albandrieu.com
  -> Scrutiny / remaining service work
  -> Docling / OpenRAG-LiteLLM
```
