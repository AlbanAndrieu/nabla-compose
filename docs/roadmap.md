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
- [x] Prometheus is `RUNNING` with Prometheus, Alertmanager, node-exporter and pfSense exporter; cAdvisor is retained separately in `apps/cadvisor/disabled.yml` and is not part of the active Prometheus lifecycle.
- [x] pfSense exporter uses the low-impact steady-state contract: 300-second Prometheus scrape, serialized collectors, `system/gateways/service`, timeout 8s; routine lifecycle audits do not invoke the expensive metrics fan-out.
- [x] OpenRAG backend + OpenSearch + global Langflow + frontend collective health are green; the remaining OpenRAG functional gap is Docling/document ingestion.
- [ ] Sentry is in its final supervised convergence pass: the 2026-09-08 redeploy created all 19 workloads, both one-shot migrations exited, `snuba-replacer` and `snuba-subscription-consumer-events` are running, but TrueNAS still reports aggregate `DEPLOYING` while healthchecks complete. Final acceptance requires `diagnose-sentry.sh --check`, healthy consumer heartbeats/topics, `RUNNING`, then the synthetic event smoke.
- [ ] Wazuh is not yet deployed; bootstrap now uses runtime API secrets and fail-closed PEM files under `/mnt/cpool/wazuh`, but runtime bootstrap/redeploy still needs acceptance.
- [ ] AutoKuma is repository-ready but still `MISSING` on TrueNAS.

## Immediate runtime stabilization gate

Finish these before expanding the platform further:

1. [x] **FastAPI Sample** — 1.13.3 deployed and observer/TLS/API acceptance green.
2. [x] **pfSense / Prometheus** — exporter pressure reduced, Prometheus RUNNING, cAdvisor removed from the active lifecycle.
3. [x] **OpenRAG runtime** — backend/OpenSearch/Langflow/frontend collective health green.
4. [ ] **Sentry — finish first** — allow the long first-start grace to complete, run `sudo bash scripts/truenas/diagnose-sentry.sh --check`, require all consumer heartbeats/topics and aggregate TrueNAS `RUNNING`, then rerun the synthetic event smoke.
5. [ ] **Docling for OpenRAG — only after Sentry** — deploy a repository-managed Docling service (or an explicit supported `DOCLING_SERVE_URL`), prove Docling health from `openrag-backend`, then validate document ingestion, indexing and search end-to-end.
6. [ ] **OpenRAG ↔ LiteLLM integration** — after Sentry is accepted and Docling is installed/healthy, activate the prepared workstation GPU route `OpenRAG -> 172.17.0.57:4000/v1`, run `bootstrap_litellm.py` then `--apply`, prove `qwen` tool-capable chat and `embedding` vectors, and finally validate the optional TrueNAS LiteLLM proxy/fallback aliases.
7. [ ] **Wazuh** — run the corrected bootstrap, create/verify the TLS material and API secret, deploy manager/indexer/dashboard, then validate the full chain before enabling optional forwarding.
8. [ ] **AutoKuma** — bootstrap the Uptime Kuma JWT and register the repository-managed Custom App.
9. [ ] **Secondary runtime debt** — repair Pyroscope readiness and Bichon OAuth2 token re-authorization; keep Suricata/pihole-dns-sync restart loops tracked separately.

**Ordering gate:** finish Sentry before starting Docling or applying the OpenRAG/LiteLLM provider configuration. Do **not** run the LiteLLM `--apply` step until Sentry acceptance is green, Docling health is green, and one end-to-end ingestion/search path is proven.

### Sentry startup note

Sentry 26.8 is intentionally slow to converge on this TrueNAS host. A deployment can remain around **70%** while the containers already exist and the aggregate app remains `DEPLOYING`; this is an orchestration-progress value, not a Sentry readiness percentage.

- consumer heartbeat healthchecks use a `start_period` of up to 600 seconds;
- one-shot `snuba-migrate` and `sentry-migrate` complete before dependent consumers converge;
- do not repeatedly redeploy while the 10-minute first-start grace is still active;
- `app.update` already applies the new Custom App Compose configuration and can start a deployment cycle. Do not immediately follow it with `app.redeploy` unless a second restart is explicitly required, because that resets the healthcheck grace window;
- for an unchanged Compose definition, use `app.redeploy` alone;
- after the grace window, run `sudo bash scripts/truenas/diagnose-sentry.sh --check` before deciding that the deployment is stuck.

Once Sentry and Wazuh are converged, resume the Kubernetes platform gate below.

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
- [ ] prove all three Talos VMs start automatically after the next TrueNAS reboot;
- [ ] run `scripts/talos/validate-cluster.sh` immediately before the network smoke;
- [ ] run `scripts/talos/smoke-kubernetes-network.sh`;
- [ ] prove CoreDNS resolution for `kubernetes.default.svc.cluster.local`;
- [ ] prove disposable Service DNS and ClusterIP routing;
- [ ] prove cross-node pod routing between workers `172.17.0.51` and `172.17.0.52`;
- [ ] run `scripts/talos/smoke-fastapi-sample.sh --preflight`;
- [ ] prove the selected Kubernetes IngressClass exists;
- [ ] prove `test.albandrieu.com` resolves before deployment;
- [ ] deploy FastAPI Sample from an immutable `@sha256:` image;
- [ ] prove Deployment rollout and ready Service endpoints;
- [ ] prove external `https://test.albandrieu.com/health`;
- [ ] prove external `https://test.albandrieu.com/v2/version`;
- [ ] retain Pod/Node/PodIP/Service/Ingress correlation evidence;
- [ ] clean up/recreate the smoke workload without affecting `sample.albandrieu.com`.

## Sentry lifecycle convergence

Functional Sentry health and TrueNAS lifecycle state remain separate gates.

- [x] inventory every Sentry container state and health while TrueNAS reports `DEPLOYING`;
- [x] distinguish successful one-shot migrations (`snuba-migrate=0`, `sentry-migrate=0`) from required steady-state services;
- [x] prove Snuba API, Sentry web, Kafka/Redis/ClickHouse network paths and Sentry ClickHouse authentication are healthy;
- [x] isolate the previously unhealthy services to `snuba-replacer` and `snuba-subscription-consumer-events`;
- [x] align consumer startup with upstream 26.8 ordering so long-running Snuba consumers wait for `sentry-migrate --create-kafka-topics`;
- [x] redeploy Sentry from the corrected repository Compose; the supervised 2026-09-08 restart created all 19 workloads, both migration jobs exited, and the previously blocked Snuba processes are running while healthchecks converge;
- [ ] allow the consumer healthcheck first-start grace (`start_period: 600s`) to elapse without another redeploy;
- [ ] run `scripts/truenas/diagnose-sentry.sh --check` after the startup grace and prove all required Kafka topics;
- [ ] require both consumer heartbeat files/healthchecks to converge to healthy;
- [ ] require TrueNAS app state to converge from `DEPLOYING` to `RUNNING`;
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
