# Homelab roadmap

Last updated: 2026-09-09.

This is the concise operational index. Detailed design, evidence and rollback
notes remain in the specialized roadmaps:

- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)

## Current platform state

- [x] Talos control plane and both workers are Kubernetes `Ready`.
- [x] kubelet, kube-proxy, CoreDNS and the Talos-managed default Flannel CNI are running; all three nodes report `NetworkUnavailable=False` / `FlannelIsUp`, and the single-control-plane etcd member is healthy.
- [x] `scripts/talos/validate-cluster.sh` provides the read-only base-cluster gate.
- [x] FastAPI Sample uses the repository-owned `sample-observer` bridge.
- [x] TrueNAS observer source is pinned to `10.254.255.9/32`.
- [x] persisted and active TrueNAS `ui_allowlist` values converge after UI restart/reconciliation.
- [x] authenticated TrueNAS WebSocket `system.version` and `app.query` succeed with TLS verification enabled.
- [x] PR #144 fixed allowlist activation so persisted state is never treated as sufficient by itself.
- [x] FastAPI Sample runtime promoted and validated on `1.13.3` (`a19676f`): health/version, observer source `10.254.255.9`, TLS verification and authenticated TrueNAS WebSocket calls are green.
- [ ] FastAPI TrueNAS observer least-privilege migration is in A/B validation: the TrueNAS-local runtime now uses `TRUENAS_API_USERNAME=fastapi_observer`; `auth.me` has matched that identity and the read gate sees 94 TrueNAS apps. FastAPI Cloud temporarily keeps `albandrieu` until A/B inventory parity is green.
- [x] Prometheus is `RUNNING` with Prometheus, Alertmanager, node-exporter and pfSense exporter; cAdvisor is retained separately in `apps/cadvisor/disabled.yml` and is not part of the active Prometheus lifecycle.
- [x] pfSense exporter uses the low-impact steady-state contract: 300-second Prometheus scrape, serialized collectors, `system/gateways/service`, timeout 8s; routine lifecycle audits do not invoke the expensive metrics fan-out.
- [x] OpenRAG backend + OpenSearch + global Langflow + frontend collective health are green; the remaining OpenRAG functional gap is Docling/document ingestion.
- [x] Sentry 26.8 lifecycle convergence is green on 2026-09-08: `diagnose-sentry.sh --check` returned `exit=0`, TrueNAS aggregate state is `RUNNING`, no workload is `starting`/`unhealthy`/unexpectedly exited, all required Kafka topics exist, Sentry edge health is green and Snuba API health is OK. The only remaining final-regression item is rerunning the synthetic event smoke after this convergence pass.
- [ ] Wazuh is not yet deployed; bootstrap now uses runtime API secrets and fail-closed PEM files under `/mnt/cpool/wazuh`, but runtime bootstrap/redeploy still needs acceptance.
- [ ] AutoKuma is repository-ready but still `MISSING` on TrueNAS.
- [x] Large checks/diagnostics use compact interactive summaries with detailed mode-`0600` reports under `/tmp`; CI/non-TTY output remains verbose. See [Diagnostic output policy](./diagnostic-output.md).

## Immediate runtime stabilization gate

**Priority #1 is now the TrueNAS-hosted FastAPI Sample runtime itself.** Before
continuing Talos/Kubara/CSI, prove that the local deployment can consume every
critical homelab API/observability dependency that it is expected to expose in
`/api`. FastAPI Cloud remains the comparison baseline where useful, but a
green cloud observation must not mask a broken local path.

1. [ ] **FastAPI Sample local dependency convergence — P0 / priority #1** —
   make the TrueNAS-hosted runtime prove, from inside the `fastapi-sample`
   container, the same intended read-only integrations used by the health board:
   TrueNAS API, pfSense API, Cloudflare API, Prometheus, local Sentry and local
   Pyroscope. Do not call the local runtime stable until all six dependencies
   have an explicit transport/auth/application-level result and failures expose
   the failing phase in `/api`.
2. [ ] **TrueNAS API local parity — first blocker** — explain why the
   TrueNAS-hosted FastAPI reports the TrueNAS observer unhealthy/unreachable
   while FastAPI Cloud can observe TrueNAS. Treat the dedicated
   `fastapi_observer` RBAC difference versus the temporary cloud
   `albandrieu` identity as one hypothesis, not the conclusion: the direct
   verification already proves `fastapi_observer` authentication,
   `APPS_READ,CATALOG_READ`, `system.version` and 94 apps from
   `app.query`. Compare the actual FastAPI runtime status, deployed revision,
   canonical environment, WebSocket path, proxy/`NO_PROXY`, DNS route,
   source allowlist and API failure phase. Require the local runtime itself to
   report `configured=true`, `reachable=true`, `stale=false` and the same
   intended app inventory before changing RBAC.
3. [ ] **pfSense API from local FastAPI** — prove the TrueNAS-hosted container
   reaches the split-DNS/LAN pfSense endpoint with the dedicated posture and
   security credentials, classify DNS/TCP/TLS/auth/response failures separately,
   and require the low-impact posture/service/Unbound path plus the intended
   security-table observation to succeed without using the public/shared-WAN
   diagnostic model.
4. [ ] **Cloudflare API from local FastAPI** — prove the local runtime can
   authenticate to the Cloudflare API with its intended read-only token/service
   credential and retrieve the account/tunnel/Access-policy evidence required by
   the health board. Distinguish Cloudflare API authorization from Cloudflare
   Access protection of public service URLs.
5. [ ] **Prometheus API from local FastAPI** — prove the local runtime can query
   the local Prometheus HTTP API, not merely that the Prometheus container is
   `RUNNING`; require a cheap instant query and the TrueNAS/pfSense/core target
   metadata used by FastAPI, with bounded timeout/cache behaviour.
6. [ ] **Sentry local API/event path** — keep the already-green Sentry lifecycle,
   then prove FastAPI can authenticate to the local Sentry API through the
   intended edge/Cloudflare path and complete the pending synthetic event smoke;
   retain event id plus Relay/Kafka/Snuba/ClickHouse evidence.
7. [ ] **Pyroscope local API/query path** — prove the local
   `http://172.17.0.24:4040` endpoint is ready and that FastAPI can query/read
   its own `service_name=fastapi-sample` profiling data; surface readiness,
   query/auth/transport failures independently instead of only checking that the
   container exists.
8. [ ] **Cross-runtime A/B report** — extend the runtime comparison so each of
   the six dependencies reports `local` versus `FastAPI Cloud` with
   configured/reachable/authenticated/application-result/stale/error-stage
   evidence. The comparison must identify which runtime failed instead of using
   generic messages such as “one runtime is unhealthy”.
9. [ ] **Runtime validation baseline** — before calling the local FastAPI runtime
   stable, run the bounded integration, non-destructive HTTP pentest and basic
   performance modes from `scripts/testing/runtime-baseline.py`. Require
   `/health` + `/v2/version` integration success, the HTTP security baseline
   to pass, and a low-volume latency/error smoke with explicit p95/error-rate
   thresholds. CI proves the harness against a deterministic local fixture; the
   live TrueNAS/public targets are explicit/manual runs.
10. [ ] **Sentry — final smoke before Docling/OpenRAG-LiteLLM** — lifecycle
   convergence is proven (`exit=0`, aggregate `RUNNING`, zero
   unhealthy/starting/unexpected exits, Kafka topics present, edge + Snuba
   healthy); finish the synthetic event proof as part of the local FastAPI gate.
11. [ ] **Kubernetes storage P0 — resumes after FastAPI local dependency convergence** —
    finish VM-autostart persistence, rerun the Talos/CoreDNS/Flannel network
    regression gate, then make TrueNAS NFS + CSI persistence green before
    Kubara/Traefik and the immutable FastAPI ingress smoke on
    `test.albandrieu.com`.
12. [ ] **Wazuh core — parallel** — bootstrap fail-closed API/TLS material,
    deploy manager/indexer/dashboard, and require
    `diagnose-wazuh.sh --check` before enabling the optional shared-OpenSearch
    forwarder.
13. [ ] **Scrutiny + InfluxDB — parallel** — preserve/recover history, provision
    a dedicated `SCRUTINY_WEB_INFLUXDB_TOKEN`, then run the explicit repository
    cutover/acceptance helper.
14. [ ] **Docling for OpenRAG — after Sentry** — deploy Docling only after the
    Sentry acceptance gate above is green, then prove document
    ingestion/index/search end-to-end.
15. [ ] **OpenRAG ↔ LiteLLM — after Docling** — only after Sentry acceptance plus
    Docling + one ingestion/search path are green, activate the workstation GPU
    route and prove chat/tool-calling + embeddings.
16. [ ] **Secondary runtime debt** — AutoKuma registration, Bichon OAuth2
    re-authorization and the separately tracked Suricata/pihole-dns-sync loops.

**Ordering gate:** the FastAPI local dependency convergence above is the first
blocking gate. Kubernetes implementation work may be prepared, but P0
acceptance resumes only after the local FastAPI runtime can prove its critical
TrueNAS/pfSense/Cloudflare/Prometheus/Sentry/Pyroscope dependencies. Once that
gate is green, treat the already-installed Talos/Flannel/CoreDNS path as a
regression gate and make **TrueNAS NFS + CSI the first remaining Kubernetes
implementation gate, before Kubara/Traefik and the external FastAPI ingress
smoke**. Persistent/stateful workloads remain blocked until CSI provisioning,
persistence, reclaim and rollback are proven. Sentry must also be accepted
before Docling/OpenRAG-LiteLLM. Wazuh/Scrutiny work may proceed in parallel
because it does not replace either acceptance gate.

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
- [x] finish the TrueNAS-local redeploy with
      `TRUENAS_API_USERNAME=fastapi_observer`; 2026-09-08 runtime evidence
      confirms canonical username/key selection, TLS verification and 94 apps;
- [x] run
      `scripts/security/verify-truenas-observer-access.sh --local`; evidence
      confirms `authenticated_username=fastapi_observer`,
      `roles=APPS_READ,CATALOG_READ`, `rbac_scope=apps_read`,
      `system.version` success and 94 apps from `app.query`;
- [ ] inspect the effective roles: prefer the narrow `APPS_READ` scope if it
      satisfies the complete FastAPI observer contract; accept
      `READONLY_ADMIN` only as an intermediate read-only state because it is
      broader than required;
- [ ] while FastAPI Cloud still uses `TRUENAS_API_USERNAME=albandrieu`, run
      `scripts/security/verify-truenas-observer-access.sh --compare-cloud` and
      require the same catalog revision plus the exact same TrueNAS application
      IDs from both runtimes; the first attempt reached comparison but one
      `/api/homelab/status` snapshot failed the health predicate, so the helper
      now reports the failing runtime and configured/reachable/stale/credential
      condition explicitly;
- [ ] **switch FastAPI Cloud to `fastapi_observer`** only after A/B parity:
      change `TRUENAS_API_USERNAME=fastapi_observer` and its paired dedicated
      `TRUENAS_API_KEY` together, keep `TRUENAS_API_VERIFY_SSL=true`,
      redeploy and prove the same inventory/production smoke before retiring the
      `albandrieu` FastAPI credential;
- [ ] rerun the FastAPI Cloud production deployment/smoke and require homelab
      status, topology, TrueNAS runtime inventory and UI smoke to remain green;
- [ ] remove the FastAPI workload's use of the `albandrieu` credential after
      rollback evidence is retained; keep human/infrastructure credentials
      outside the application observer boundary.

## P0 — Kubernetes platform: TrueNAS NFS + CSI first

The Talos/Kubernetes base is already operational. Talos v1.13 installs Flannel
as its default CNI unless explicitly disabled, and CoreDNS is deployed during
cluster bootstrap unless explicitly disabled. Repository runtime evidence
already confirms CoreDNS, kube-proxy and Flannel are running, all three nodes
are `Ready`, and `NetworkUnavailable=False` reports `FlannelIsUp`.

Do **not** reinstall Flannel or CoreDNS. Keep the network checks as a regression
gate around storage changes. The first remaining implementation phase is
TrueNAS-backed NFS/CSI persistence.

### P0.A — Talos/Kubernetes baseline — already present

- [x] Kubernetes `v1.36.3` runs on all three Talos `v1.13.9` nodes;
- [x] control plane `172.17.0.50` and workers `172.17.0.51` / `172.17.0.52` are `Ready`;
- [x] Talos-managed Flannel is installed and all nodes report `NetworkUnavailable=False` / `FlannelIsUp`;
- [x] CoreDNS, kube-proxy and Flannel pods are running;
- [x] Talos API TCP/50000 reachability is restored on all three nodes;
- [ ] apply the IaC autostart change only if the plan is exactly 3 in-place VM updates, 0 create and 0 destroy;
- [ ] run `scripts/truenas/verify-talos-vm-autostart.sh --check` and require all three VMs to report `autostart=true` and `RUNNING`;
- [ ] prove all three Talos VMs start automatically after the next TrueNAS reboot;
- [ ] rerun `scripts/talos/validate-cluster.sh` and `scripts/talos/smoke-kubernetes-network.sh` immediately before CSI changes as regression proof for CoreDNS, Service/ClusterIP and cross-node routing;
- [ ] before production workload migration, decide whether to enable Talos 1.13 Flannel NetworkPolicy enforcement with `kubeNetworkPoliciesEnabled: true`; without it, NetworkPolicy objects are accepted but not enforced by the default Flannel path.

### P0.B — TrueNAS NFS + CSI — active first implementation gate

TrueNAS already exposes NFSv4 on `172.17.0.24:2049`, and the parent dataset
`cpool/k8s/csi` already exists. Talos ships the NFS client in its maintained
kubelet image, so the first NFS-backed CSI path does not require an extra
`nfs-utils` Talos system extension.

Prefer the reviewed NFSv4.x path for this homelab. Do not select NFSv3 merely
because an example chart uses it; Talos does not run `rpc.statd`, so NFSv3
locking needs special handling such as `nolock`.

- [ ] run the read-only `scripts/talos/validate-csi-prereqs.sh`;
- [ ] verify the chosen NFS export/path and allowed client networks cover both workers, not only the workstation running the preflight;
- [ ] select and pin the reviewed `democratic-csi` release/chart and NFS driver values;
- [ ] create a dedicated least-privilege TrueNAS CSI identity; never reuse `fastapi_observer` or the OpenTofu/Terragrunt credential;
- [ ] keep CSI API credentials in a Kubernetes Secret rendered from the approved secret source, never in Git;
- [ ] constrain dynamic provisioning below `cpool/k8s/csi` and document the corresponding TrueNAS NFS share/export contract;
- [ ] create an explicit `StorageClass` (initial target: `nabla-truenas-nfs`) and decide separately whether it should become the default class;
- [ ] dynamically provision a disposable PVC/PV and require `Bound`;
- [ ] mount the PVC on a worker Pod, write a marker and prove read/write;
- [ ] recreate the Pod and prove the marker survives;
- [ ] reschedule the persistence smoke onto the other worker and prove the NFS-backed volume remains usable;
- [ ] prove reclaim/cleanup behavior and retain at least one rollback path before allowing stateful workloads.

### P0.C — Kubara/Traefik + FastAPI ingress — only after CSI

Kubara remains pinned to `v0.14.0`, but ingress is no longer a prerequisite
for CSI. Start this phase only after P0.B persistence and rollback are green.

- [x] pin Kubara `v0.14.0` in `config/kubara/VERSION` and retain the read-only `scripts/talos/preflight-kubara.sh` ownership contract;
- [ ] run `scripts/talos/preflight-kubara.sh --pre-bootstrap`, then `kubara generate --helm`;
- [ ] inspect the generated Traefik Service exposure mode. On this local/bare-metal cluster, do not assume a cloud `LoadBalancer` implementation exists: explicitly select the existing HAProxy/NodePort or host-network path, or deliberately add a reviewed bare-metal load-balancer implementation such as MetalLB/kube-vip if the generated platform requires `type: LoadBalancer`;
- [ ] bootstrap/reconcile the minimal Kubara platform and require exactly one intended Traefik `IngressClass`/controller;
- [ ] run `scripts/talos/smoke-fastapi-sample.sh --preflight`;
- [ ] prove no existing Ingress claims `test.albandrieu.com` and prove its DNS/edge route;
- [ ] deploy FastAPI Sample from an immutable `@sha256:` image;
- [ ] prove Deployment rollout and ready Service EndpointSlice addresses;
- [ ] prove external `https://test.albandrieu.com/health`;
- [ ] prove external `https://test.albandrieu.com/v2/version`;
- [ ] attach the already-proven CSI StorageClass/PVC to the final acceptance workload when useful, without making storage debugging depend on ingress;
- [ ] retain Pod/Node/PodIP/Service/Ingress correlation evidence and clean up/recreate the smoke workload without affecting `sample.albandrieu.com`.

## Sentry lifecycle convergence — final acceptance pending

Sentry remains ahead of Docling/OpenRAG-LiteLLM until this gate is complete.

- [x] both one-shot migrations have exited after the current redeploy;
- [x] all 19 workloads are created;
- [x] `snuba-replacer` and `snuba-subscription-consumer-events` are running in the current supervised snapshot;
- [x] allow the 600-second first-start healthcheck grace to elapse without another redeploy;
- [x] run `scripts/truenas/diagnose-sentry.sh --check` and prove the required Kafka topics plus consumer heartbeat health (`exit=0`, `ok=8`, `failed=0`, `warnings=0` on 2026-09-08);
- [x] require no unexpected `starting`/`unhealthy` steady-state workload (`starting_health=0`, `unhealthy=0`, `unexpected_exited=0`);
- [x] require TrueNAS aggregate state to converge from `DEPLOYING` to `RUNNING`;
- [ ] rerun the synthetic Sentry event smoke and preserve edge -> Relay -> Kafka -> Snuba -> ClickHouse evidence as the final regression proof.


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
