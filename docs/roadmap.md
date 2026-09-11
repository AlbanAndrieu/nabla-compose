# Homelab roadmap

Last updated: 2026-09-12.

This file is the concise operational index. Detailed design, incident evidence and rollback procedures stay in the specialized documents:

- [Homelab ordered reboot runbook](./homelab-reboot-runbook.md)
- [TrueNAS reboot incident · 2026-09-11](./truenas-reboot-incident-20260911.md)
- [Sentry Taskbroker / Relay project-config incident · 2026-09-11](./sentry-taskbroker-project-config-incident-20260911.md)
- [Functional observability exporters](./observability-exporters.md)

## Current platform state

- [x] Talos `v1.13.9` / Kubernetes `v1.36.3`: control plane `172.17.0.50`, workers `172.17.0.51` / `172.17.0.52`, all Ready after reboot.
- [x] TrueNAS controlled reboot completed and accepted.
- [x] TrueNAS CSI RWX acceptance is green.
- [x] Langfuse post-reboot runtime is green; OpenRAG core is green.
- [ ] **Docling / OpenRAG ingest:** native `docling-serve` is stopped, so OpenRAG knowledge ingestion remains unavailable until Docling is restored and validated.
- [x] **Sentry ingestion incident resolved:** Taskbroker is stable, Taskworker can reach `taskbroker:50051`, Kafka group `taskworker` has an active member with lag `1`, Taskbroker SQLite is active, `diagnose-sentry.sh --check` reports `ok=8 failed=0 warnings=0`, and `smoke-sentry-event.sh` proves `edge -> Relay -> Kafka -> ingest -> Snuba -> ClickHouse` with the synthetic event queryable in ClickHouse. Detailed post-mortem: [`sentry-taskbroker-project-config-incident-20260911.md`](./sentry-taskbroker-project-config-incident-20260911.md).
- [x] **Exporter conflict preflight:** TrueNAS Netdata is active; ports/listeners `8125`, `9125`, `9102`, `9308` were free with no Docker publisher conflicts. StatsD remains deferred; Kafka exporter remains a separate controlled Kafka App lifecycle change.
- [ ] **Prometheus target debt:** reconcile stale/down scrapes; Mimir remains high priority because remote-write also targets it.
- [x] **Suricata engine/rules:** capture on TrueNAS `br0`, rules loaded and `eve.json` active.
- [ ] **Suricata downstream consumption:** prove CrowdSec/Alloy/central observability consumes current EVE.
- [ ] **pfSense NetFlow -> Cloudflare Network Analytics:** restore flow export path and prove fresh flow arrival end to end.

## P0 — controlled TrueNAS reboot accepted

The 2026-09-11 transaction is operationally accepted. Historical manifest verification remains strict for forensic visibility.

- [x] Reboot TrueNAS through supported middleware.
- [x] Validate Docker/IPAM/br0/observer network postconditions.
- [x] Validate Talos/Kubernetes readiness.
- [x] Validate post-reboot CSI provisioning, publishContext, cross-worker RWX and reclaim.
- [x] Resume required platform services sufficiently for baseline acceptance.

## P0.1 — reboot lifecycle hardening

- [x] Normalize TrueNAS `system.ready` representation.
- [x] Persist prepare/reboot transaction state and immutable manifest identity.
- [x] Add guarded Docker/containerd orphan-shim diagnosis/recovery.
- [x] Add manifest-aware idempotent resume reconciliation.
- [ ] Add explicit operator-acceptance/deferred annotations without weakening strict verification.
- [ ] Add interrupted-prepare and ghost-runtime fixtures.
- [ ] Continue reducing `no topology mapping` and add health-aware dependency acceptance.

## P0.2 — CSI hardening

- [x] Dynamic provisioning, controller publishContext, cross-worker RWX and fresh reclaim are green.
- [ ] Verify bounded TrueNAS NFS share and ZFS dataset disappearance after Kubernetes reclaim.
- [ ] Harden smoke Pods toward Restricted PSS.
- [ ] Evaluate democratic-csi upgrade only after baseline stability.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27.

## P1 — infrastructure secrets

1. [ ] OpenTofu/Terragrunt and Garage backend credentials.
2. [ ] Dedicated TrueNAS infrastructure automation identity.
3. [ ] Nexus automation credentials.
4. [ ] Talos/Kubernetes/CSI machine credentials.
5. [ ] Root-owned `0600` runtime rendering.
6. [ ] Retain encrypted recovery material.
7. [ ] Move long-lived machine secrets to Vault/OpenBao after persistence/rollback is proven.

## P2 — platform/security tools

- [ ] Vault/OpenBao after CSI/reboot acceptance.
- [ ] Falco after infrastructure baseline stabilizes.
- [ ] Kubara config/bootstrap.
- [ ] Traefik/Kubara ingress with explicit bare-metal exposure.
- [ ] FastAPI Kubernetes smoke on `test.albandrieu.com` after storage/ingress ownership is stable.

## P3 — runtime/services

- [x] Prometheus, Grafana, Graylog baseline, CrowdSec resume intent, Langflow, Wazuh core and OpenRAG core exist.
- [x] Langfuse post-reboot runtime acceptance is green.
- [x] **Sentry Taskbroker/Kafka/Relay ingestion recovery:** Taskbroker bootability restored, effective StatsD default resolves, Taskworker->Taskbroker gRPC reachable, Kafka `taskworker` consumer rejoined, lag drained to `1`, Relay project-config path recovered and full synthetic Sentry event is persisted in ClickHouse.
- [ ] **Sentry upstream/version debt:** monitor self-hosted 26.8 Taskbroker Kafka coordinator/session-timeout behavior. Functional health must include Taskworker->Taskbroker reachability, active Kafka membership/lag and end-to-end ingestion; container/process health alone is insufficient.
- [x] **Exporter conflict preflight:** no listener/publisher conflict on planned StatsD/Kafka exporter ports.
- [ ] **Kafka exporter:** deploy only in a controlled Kafka App update window after preserving the accepted Sentry functional baseline.
- [ ] **StatsD exporter:** remains deferred until separately justified; do not change Taskbroker metrics destination as a recovery workaround.
- [ ] **Prometheus DOWN-target reconciliation:** repair or intentionally remove stale scrapes; fix Mimir first.
- [x] **Suricata capture + rules/EVE acceptance**.
- [ ] **Suricata downstream consumption**.
- [ ] **pfSense NetFlow -> Cloudflare Network Analytics**.
- [ ] Scrutiny: finish TrueNAS SMART acceptance plus workstation collector.
- [ ] Uptime Kuma + AutoKuma Compose ownership.
- [ ] Homarr idempotent bootstrap/topology sync.
- [ ] Native TrueNAS -> Compose migration planning for PostgreSQL/AdGuard Home.
- [ ] Deferred service debt: nginx-proxy-manager, OpenArchiver, Paperless-ngx.
- [ ] Docling restore, then OpenRAG document ingestion acceptance and LiteLLM integration.
