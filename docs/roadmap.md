# Homelab roadmap

Last updated: 2026-09-08.

This is the concise operational index. Detailed design, evidence and rollback
notes remain in the specialized roadmaps:

- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)

## Current platform state

- [x] Talos control plane and both workers are Kubernetes `Ready`.
- [x] kubelet/flannel are healthy and the single-control-plane etcd member is healthy.
- [x] `scripts/talos/validate-cluster.sh` provides the read-only base-cluster gate.
- [x] FastAPI Sample uses the repository-owned `sample-observer` bridge.
- [x] TrueNAS observer source is pinned to `10.254.255.9/32`.
- [x] persisted and active TrueNAS `ui_allowlist` values converge after UI restart/reconciliation.
- [x] authenticated TrueNAS WebSocket `system.version` and `app.query` succeed with TLS verification enabled.
- [x] PR #144 fixed allowlist activation so persisted state is never treated as sufficient by itself.
- [x] FastAPI Sample runtime promoted and validated on `1.13.3` (`a19676f`): health/version, observer source `10.254.255.9`, TLS verification and authenticated TrueNAS WebSocket calls are green.
- [ ] FastAPI TrueNAS observer least-privilege migration is in A/B validation: the TrueNAS-local runtime is being redeployed on FastAPI Sample `1.13.5` with `TRUENAS_API_USERNAME=fastapi_observer`; FastAPI Cloud temporarily keeps `albandrieu` as the comparison baseline until identity/RBAC and inventory-parity gates are green.
- [x] Prometheus is `RUNNING` with Prometheus, Alertmanager, node-exporter and pfSense exporter; cAdvisor is retained separately in `apps/cadvisor/disabled.yml` and is not part of the active Prometheus lifecycle.
- [x] pfSense exporter uses the low-impact steady-state contract: 300-second Prometheus scrape, serialized collectors, `system/gateways/service`, timeout 8s; routine lifecycle audits do not invoke the expensive metrics fan-out.
- [x] OpenRAG backend + OpenSearch + global Langflow + frontend collective health are green; the remaining OpenRAG functional gap is Docling/document ingestion.
- [ ] Sentry 26.8 is in its final supervised convergence pass. Latest runtime evidence shows all 19 workloads created, both one-shot migrations exited, `snuba-replacer` and `snuba-subscription-consumer-events` running, but TrueNAS still reports aggregate `DEPLOYING` while the long healthcheck grace completes. Do not mark Sentry complete until `scripts/truenas/diagnose-sentry.sh --check`, aggregate `RUNNING`, and the synthetic-event smoke are green.
- [ ] Wazuh is not yet deployed; bootstrap now uses runtime API secrets and fail-closed PEM files under `/mnt/cpool/wazuh`, but runtime bootstrap/redeploy still needs acceptance.
- [ ] AutoKuma is repository-ready but still `MISSING` on TrueNAS.
- [x] Large checks/diagnostics use compact interactive summaries with detailed mode-`0600` reports under `/tmp`; CI/non-TTY output remains verbose. See [Diagnostic output policy](./diagnostic-output.md).

## Immediate runtime stabilization gate

The active wave is **Talos P0 + Sentry final convergence**, with Wazuh and
Scrutiny stabilization in parallel. **Docling and OpenRAG/LiteLLM activation
remain blocked until Sentry acceptance is complete.**

1. [x] **FastAPI Sample** — runtime/observer/TLS/API acceptance green.
2. [x] **pfSense / Prometheus** — low-impact exporter profile and Prometheus runtime green.
3. [ ] **Sentry — finish before Docling/OpenRAG-LiteLLM** — allow the first-start grace to complete, run `sudo bash scripts/truenas/diagnose-sentry.sh --check`, require consumer heartbeats/topics and aggregate TrueNAS `RUNNING`, then rerun the synthetic event smoke.
4. [ ] **Talos P0 — active** — apply/prove VM autostart, run the base-cluster validator, then DNS/CNI, CoreDNS, Service/ClusterIP, cross-node routing and the immutable FastAPI smoke on `test.albandrieu.com`.
5. [ ] **Wazuh core — parallel** — bootstrap fail-closed API/TLS material, deploy manager/indexer/dashboard, and require `diagnose-wazuh.sh --check` before enabling the optional shared-OpenSearch forwarder.
6. [ ] **Scrutiny + InfluxDB — parallel** — preserve/recover history, provision a dedicated `SCRUTINY_WEB_INFLUXDB_TOKEN`, then run the explicit repository cutover/acceptance helper.
7. [ ] **Docling for OpenRAG — after Sentry** — deploy Docling only after the Sentry acceptance gate above is green, then prove document ingestion/index/search end-to-end.
8. [ ] **OpenRAG ↔ LiteLLM — after Docling** — only after Sentry acceptance plus Docling + one ingestion/search path are green, activate the workstation GPU route and prove chat/tool-calling + embeddings.
9. [ ] **Secondary runtime debt** — AutoKuma registration, Pyroscope readiness, Bichon OAuth2 re-authorization and the separately tracked Suricata/pihole-dns-sync loops.

**Ordering gate:** Sentry must be accepted before Docling/OpenRAG-LiteLLM.
CSI still waits for the complete Kubernetes P0 networking and ingress smoke.
Wazuh/Scrutiny work may proceed in parallel because it does not replace either
acceptance gate.

### Sentry startup note — long 70% plateau

A Sentry 26.8 deployment can remain around **70%** in TrueNAS for several
minutes while the containers already exist and the aggregate app remains
`DEPLOYING`. The percentage is an orchestration-progress value, not a Sentry
readiness percentage.

- consumer heartbeat healthchecks use a first-start grace of up to 600 seconds;
- `snuba-migrate` and `sentry-migrate` are expected one-shot services and may already be exited while steady-state consumers continue starting;
- do not repeatedly redeploy during that grace window;
- `app.update` already applies a changed Custom App Compose definition and can start a deployment cycle. Do not immediately follow it with an unnecessary `app.redeploy`, because that starts another cycle and resets healthcheck grace;
- use `app.redeploy` alone when the stored Compose configuration is unchanged and only a restart is intended;
- after approximately 10 minutes, run `sudo bash scripts/truenas/diagnose-sentry.sh --check` before deciding that the deployment is stuck.

## FastAPI TrueNAS observer least-privilege migration

This security hardening runs in parallel with Talos P0 and does not change the
platform execution order above. The goal is to remove the human/admin identity
from FastAPI after proving that the dedicated observer has complete read
visibility.

- [x] FastAPI Sample #223 requires only the canonical
      `TRUENAS_API_USERNAME` + `TRUENAS_API_KEY` pair; legacy, MCP and
      `TRUENAS_INFRA_*` credentials are ignored rather than used as fallbacks;
- [ ] finish the TrueNAS-local redeploy on FastAPI Sample `1.13.5` with
      `TRUENAS_API_USERNAME=fastapi_observer`;
- [ ] run
      `scripts/security/verify-truenas-observer-access.sh --local` and require
      `auth.me` to report `fastapi_observer`, no write/admin RBAC role,
      TLS verification, `system.version` success and `app.query` success;
- [ ] inspect the effective roles: prefer the narrow `APPS_READ` scope if it
      satisfies the complete FastAPI observer contract; accept
      `READONLY_ADMIN` only as an intermediate read-only state because it is
      broader than required;
- [ ] while FastAPI Cloud still uses `TRUENAS_API_USERNAME=albandrieu`, run
      `scripts/security/verify-truenas-observer-access.sh --compare-cloud` and
      require the same catalog revision plus the exact same TrueNAS application
      IDs from both runtimes;
- [ ] switch FastAPI Cloud to a dedicated `fastapi_observer` API key only
      after the A/B comparison is green;
- [ ] rerun the FastAPI Cloud production deployment/smoke and require homelab
      status, topology, TrueNAS runtime inventory and UI smoke to remain green;
- [ ] remove the FastAPI workload's use of the `albandrieu` credential after
      rollback evidence is retained; keep human/infrastructure credentials
      outside the application observer boundary.

## P0 — Kubernetes DNS/CNI + FastAPI Sample acceptance

Do not start CSI installation until all items below are green.

Reboot incident resolved (2026-09-08): all three Talos VMs were found
`STOPPED` after the TrueNAS reboot because their persisted VM configuration
still had `autostart=false`. Manual start restored direct LAN reachability,
ICMP and Talos API TCP/50000 on `.50`, `.51` and `.52`.

Steady-state remediation is now tracked in IaC with
`TALOS_VM_AUTOSTART=true`. Apply only if the reviewed plan is exactly three
in-place VM updates with zero create/replace/destroy actions.

- [x] restore and prove Talos API TCP/50000 reachability on `.50`, `.51` and `.52` after manual VM start;
- [ ] apply the IaC autostart change only if the plan is exactly 3 in-place VM updates, 0 create and 0 destroy;
- [ ] run `scripts/truenas/verify-talos-vm-autostart.sh --check` and require all three VMs to report `autostart=true` and `RUNNING`;
- [ ] prove all three Talos VMs start automatically after the next TrueNAS reboot and rerun the persistence gate;
- [ ] run `scripts/talos/validate-cluster.sh` immediately before the network smoke;
- [ ] run `scripts/talos/smoke-kubernetes-network.sh`;
- [ ] prove CoreDNS resolution for `kubernetes.default.svc.cluster.local`;
- [ ] prove disposable Service DNS and ClusterIP routing;
- [ ] prove cross-node pod routing between workers `172.17.0.51` and `172.17.0.52`;
- [ ] run `scripts/talos/smoke-fastapi-sample.sh --preflight`;
- [ ] prove the selected Kubernetes IngressClass has a controller and no existing
      Ingress already claims `test.albandrieu.com`;
- [ ] prove `test.albandrieu.com` resolves before deployment;
- [ ] deploy FastAPI Sample from an immutable `@sha256:` image;
- [ ] prove Deployment rollout and ready Service EndpointSlice addresses;
- [ ] prove external `https://test.albandrieu.com/health`;
- [ ] prove external `https://test.albandrieu.com/v2/version`;
- [ ] retain Pod/Node/PodIP/Service/Ingress correlation evidence;
- [ ] clean up/recreate the smoke workload without affecting `sample.albandrieu.com`.

## Sentry lifecycle convergence — final acceptance pending

Sentry remains ahead of Docling/OpenRAG-LiteLLM until this gate is complete.

- [x] both one-shot migrations have exited after the current redeploy;
- [x] all 19 workloads are created;
- [x] `snuba-replacer` and `snuba-subscription-consumer-events` are running in the current supervised snapshot;
- [ ] allow the 600-second first-start healthcheck grace to elapse without another redeploy;
- [ ] run `scripts/truenas/diagnose-sentry.sh --check` and prove the required Kafka topics plus consumer heartbeat health;
- [ ] require no unexpected `starting`/`unhealthy` steady-state workload;
- [ ] require TrueNAS aggregate state to converge from `DEPLOYING` to `RUNNING`;
- [ ] rerun the synthetic Sentry event smoke and preserve edge -> Relay -> Kafka -> Snuba -> ClickHouse evidence as the final regression proof.

## P0.1 — TrueNAS-backed Kubernetes CSI

Start only after the complete P0 network/ingress smoke is green.

- [ ] run the read-only CSI preflight;
- [ ] select/pin the reviewed CSI implementation;
- [ ] create a dedicated least-privilege TrueNAS CSI identity;
- [ ] provision storage below `cpool/k8s/csi`;
- [ ] create an explicit StorageClass;
- [ ] attach a disposable PVC to the FastAPI Sample smoke;
- [ ] prove data survives Pod recreation;
- [ ] prove reclaim/cleanup and at least one rollback path.

NFS remains the first persistence smoke path unless a separate architecture
review selects another transport.

## P1 — infrastructure secrets

After CSI persistence/rollback is proven:

1. OpenTofu/Terragrunt + Garage backend credentials;
2. dedicated TrueNAS automation credentials (`TRUENAS_INFRA_API_USERNAME` + `TRUENAS_INFRA_API_KEY`), never the FastAPI observer pair;
3. Nexus automation credentials;
4. Talos/Kubernetes/CSI credentials;
5. Vaultwarden-backed rendering into minimum root-owned `0600` runtime files;
6. retain git-crypt as encrypted recovery material;
7. move long-term machine secrets to Vault/OpenBao only after Kubernetes storage is proven.

## P2/P3 — core services and migrations

Current status after runtime stabilization:

1. [x] Prometheus core runtime;
2. [x] Grafana runtime;
3. [x] Graylog runtime;
4. [x] CrowdSec runtime;
5. [ ] Scrutiny repository migration + standalone InfluxDB acceptance;
6. [x] Langflow runtime;
7. [ ] AutoKuma TrueNAS registration;
8. [ ] OpenRAG **Docling ingestion** acceptance (core runtime already green);
9. [ ] Wazuh manager/indexer/dashboard acceptance;
10. [x] Akvorado runtime start; validate ingestion/query path before calling it complete;
11. [ ] ntopng / Suricata reconciliation;
12. [ ] Pi-hole and remaining application cutovers.

## P4 — identity

Keycloak/GitHub SSO and Vault/OpenBao human authentication remain after the
network, storage and infrastructure-secret gates.
