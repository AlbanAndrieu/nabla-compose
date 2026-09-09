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
- [ ] Sentry 26.8 remains externally functional but aggregate `DEPLOYING` until every Kafka-backed heartbeat is stable. The 2026-09-09 coordinator incident first affected `snuba-subscription-consumer-events` + `snuba-replacer`; targeted recovery restored both and recreated `snuba-events-subscriptions-consumers`/`snuba-replacers`. The same incident then surfaced on `sentry-events-consumer` + `sentry-attachments-consumer`. The recovery helper now restarts only unhealthy allow-listed consumers, waits a full stability cycle and checks their Kafka groups; do not redeploy all 19 containers.
- [x] Wazuh core converged on 2026-09-09 after fixing TLS private-key ownership and removing stale `nabla-compose-pr168` bind paths. Accepted evidence: TrueNAS `RUNNING`, Indexer HTTP 401, Manager API HTTP 401, Dashboard HTTP 302, `vm.max_map_count=1048576`. The optional shared-OpenSearch forwarder remains a separate gate.
- [ ] AutoKuma is repository-ready but still `MISSING` on TrueNAS.
- [x] Pull-request security now includes CodeQL SAST plus a live FastAPI Cloud production smoke; OWASP ZAP DAST runs only on `master`/daily to control CI cost, with a pfSense-safe read-only FastAPI OpenAPI scan, a passive TrueNAS API surface scan, and a passive `sample.albandrieu.com` web scan, while every PR requires the latest successful master DAST baseline to be no older than 36 hours.
- [x] API-aware DAST policy — master ZAP now includes a safe-mode filtered FastAPI OpenAPI scan plus a passive TrueNAS `/api/versions` scan when the generic runner is permitted and a passive zero-spider `sample.albandrieu.com` web scan; pfSense TCP/10443 is explicitly excluded from ZAP and load-generating tests and remains on low-frequency posture/observer checks.
- [ ] FastAPI Cloud response-header hardening — production currently lacks `X-Content-Type-Options: nosniff`, anti-framing (`X-Frame-Options` or CSP `frame-ancestors`) and HSTS. CI carries only these three explicit temporary baseline exceptions; remove each exception when the production header is fixed.
- [x] First real master DAST executed on 2026-09-09: ZAP crawled 18 URLs with `FAIL-NEW=0`; the initial strict policy failed only because nine passive WARN categories were treated as fatal. The follow-up keeps those WARNs visible, promotes high-signal rules to explicit `FAIL`, splits filtered FastAPI API versus TrueNAS API transport coverage, and excludes pfSense/Snort/pfBlocker plus aggregate health routes from the API DAST input to avoid appliance load.
- [ ] ZAP passive hardening backlog — review cache-control (10015), cross-domain JavaScript (10017), CSP (10038), cacheability (10049), Permissions-Policy (10063), private-IP disclosure on `/sickz` (rule 2), SRI (90003) and COEP (90004). `Modern Web Application` (10109) is informational; do not blanket-ignore the remaining warnings.
- [ ] GitHub merge enforcement — make `SAST / CodeQL (Python)`, `Production pre/post-deploy smoke`, `DAST master baseline gate` and the agent/pre-commit quality gate required on `master`. #161 merged while MegaLinter was still running, proving workflow presence alone is not sufficient; no repository Ruleset is currently exposed and the connected GitHub App cannot mutate classic branch protection.
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
   TrueNAS-local targets remain explicit/manual runs, while the FastAPI Cloud
   production target is checked automatically before merge and after `master`
   changes.
10. [ ] **Sentry — final smoke before Docling/OpenRAG-LiteLLM** — lifecycle
   convergence is proven (`exit=0`, aggregate `RUNNING`, zero
   unhealthy/starting/unexpected exits, Kafka topics present, edge + Snuba
   healthy); finish the synthetic event proof as part of the local FastAPI gate.
11. [ ] **Kubernetes storage P0 — resumes after FastAPI local dependency convergence** —
    TrueNAS operator binaries are now installed persistently under
    `/mnt/cpool/tools/bin` (`kubectl v1.36.3`, `talosctl v1.13.9`).
    Root owns tool installation/upgrades; `albandrieu` is the non-root cluster
    operator. Next restore private `talosconfig` + `kubeconfig` under
    `~/.config/nabla/talos`, run the operator check, finish VM-autostart
    persistence, rerun the Talos/CoreDNS/Flannel network regression gate, then
    make TrueNAS NFS + CSI persistence green before Kubara/Traefik and the
    immutable FastAPI ingress smoke on `test.albandrieu.com`.
12. [x] **Wazuh core — converged 2026-09-09** — TLS ownership repaired, stale PR-worktree mounts removed, TrueNAS aggregate state is `RUNNING`, indexer returns `401`, manager API `401`, dashboard `302`, and the optional forwarder remains disabled pending the separate shared-OpenSearch integration gate.
13. [ ] **Scrutiny + InfluxDB — parallel** — the migration-token fix is now validated on TrueNAS: the legacy authorization `114da3d49d117000` was revoked, the replacement secret is root-owned mode `0600`, `bootstrap-scrutiny-influxdb.sh --check` reports `token=VALID scope=v2`, and `deploy-scrutiny.sh --check` discovers `/dev/sda` through `/dev/sdd` with `target=MISSING ready=APPLY`. A reviewed fresh cutover has now been started with `SCRUTINY_RESET_SQLITE=1`; acceptance remains pending until TrueNAS reports `RUNNING`, the web/API is healthy, the TrueNAS collector sees SMART devices, and the workstation collector is proven to submit its own inventory. The helper continues to reuse healthy shared InfluxDB instead of redeploying it. After web health is green, complete TrueNAS SMART collection and the workstation collector submission,
    then prove the existing workstation collector posts its own SMART inventory to
    `http://172.17.0.24:31054`. The helper discovers TrueNAS host disks with
    `smartctl --scan-open`, renders explicit device passthrough for the collector,
    adds `SYS_ADMIN` only when NVMe is detected, and fails acceptance if the
    running collector cannot see any SMART devices.
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

### TrueNAS platform compatibility debt — BETA.2 + CSI auth

Keep these two upgrade debts coupled and visible before the next TrueNAS major
transition:

- [ ] **Leave TrueNAS `26.0.0-BETA.2` deliberately pinned until a reviewed
  stable-26.x upgrade window is prepared.** Before upgrading, capture the
  boot-environment/config backup, verify `cpool`, Apps/Compose datasets,
  Talos VM autostart/networking and NFS, then validate the pinned
  `truenas/api_client`, `PjSalty/truenas` provider, observer/MCP clients and
  CSI path against the target release. After the upgrade, rerun the TrueNAS,
  Talos, application and storage acceptance gates before deleting the rollback
  boot environment.
- [ ] **Remove the TrueNAS CSI v1.0.3 authentication compatibility bridge.**
  Upstream still calls deprecated `auth.login_with_api_key` on TrueNAS 26.
  Upgrade/patch the CSI client to the modern username + API-key SCRAM flow and
  prove dynamic NFS provisioning/reclaim with that path **before TrueNAS 27**,
  where the legacy method must not be assumed available.

Do not resolve either debt by independently upgrading the TrueNAS host, API
client/provider or CSI driver: treat them as one compatibility matrix and keep
the current NFS smoke/rollback proof as the acceptance gate.

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

The first implementation now selects the official `truenas/truenas-csi`
driver pinned to **v1.0.3**, because it targets TrueNAS SCALE 25.10+ and uses
the modern `/api/current` WebSocket API required by TrueNAS 26. The repository
carries an NFS-only Talos manifest: no `iscsiadm`, no iSCSI host mounts and no
snapshot/attacher sidecars are introduced for this gate.

- [x] select and pin TrueNAS CSI `v1.0.3` and its Kubernetes sidecars;
- [x] add the NFS-only Talos driver manifest plus explicit non-default `nabla-truenas-nfs` StorageClass;
- [x] constrain provisioning to `cpool/k8s/csi`, NFSv4.1 and worker-only NFS clients `172.17.0.51/32,172.17.0.52/32`;
- [x] keep the CSI API key runtime-only: `scripts/talos/install-truenas-csi-nfs.sh` renders the Kubernetes Secret without committing or printing it;
- [x] add `scripts/talos/smoke-truenas-csi-nfs.sh` to prove PVC `Bound`, worker-A write, pod recreation and worker-B persistence;
- [ ] create a dedicated least-privilege TrueNAS CSI identity/API key; never reuse `fastapi_observer` or the OpenTofu/Terragrunt credential;
- [ ] run the read-only `scripts/talos/validate-csi-prereqs.sh`;
- [ ] verify the NFS client network contract covers both workers and no conflicting `csi.truenas.io` owner already exists;
- [ ] run `scripts/talos/install-truenas-csi-nfs.sh --apply` with the dedicated runtime API key;
- [ ] dynamically provision the disposable RWX PVC and require `Bound`;
- [ ] run the cross-worker persistence smoke and require the same marker on worker B;
- [ ] prove PVC deletion removes the dynamically-created TrueNAS share/dataset according to `reclaimPolicy: Delete`;
- [ ] document and test one rollback/uninstall path before allowing stateful workloads;
- [ ] track upstream replacement of deprecated `auth.login_with_api_key`; do not carry that compatibility bridge into TrueNAS 27.

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
- [ ] require no unexpected `starting`/`unhealthy` steady-state workload. The 2026-09-09 Kafka coordinator incident first affected two Snuba consumers and then `sentry-events-consumer` plus `sentry-attachments-consumer`; targeted restarts recovered the first pair but the latter pair still need the same bounded recovery/stability proof.
- [ ] require TrueNAS aggregate state to converge from `DEPLOYING` to `RUNNING` after all Kafka-backed consumer heartbeats are stable;
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
9. [x] Wazuh manager/indexer/dashboard acceptance;
10. [x] Akvorado runtime start; validate ingestion/query path before calling it complete;
11. [ ] ntopng / Suricata reconciliation;
12. [ ] Pi-hole and remaining application cutovers.

## P4 — identity

Keycloak/GitHub SSO and Vault/OpenBao human authentication remain after the
network, storage and infrastructure-secret gates.


## Script architecture refactor

The repository now has **67 files under `scripts/`**, including **21 TrueNAS
operator scripts**. The current diagnostics duplicate the same middleware,
Docker, probe, secret and reporting primitives, so the next maintainability
gate is to refactor them without breaking existing operator entrypoints.

Reference design: `docs/operator-scripts-refactor.md`.

### P1 — reusable operator library

- [ ] extract `scripts/lib/common.sh` for strict runtime helpers,
  `require_command`, root/operator checks, temp files and cleanup traps;
- [ ] extract `scripts/lib/diagnostic.sh` for ok/fail/warn/skipped counters,
  compact/full output, report files and stable exit codes;
- [ ] extract `scripts/lib/truenas.sh` for `app.query`, app state,
  recent jobs, lifecycle evidence, canonical worktree detection and bounded
  app-state waits;
- [ ] extract `scripts/lib/docker.sh` for container state/health/restarts,
  health history, mounts/networks, bounded logs, process/resource context and
  stable-health waits;
- [ ] extract `scripts/lib/probe.sh` for HTTP/HTTPS/TCP/DNS probes,
  accepted-status sets and bounded retry/backoff;
- [ ] extract `scripts/lib/secrets.sh` for owner/mode/key-presence contracts
  without printing secret values;
- [ ] extract a guarded `scripts/lib/startup-capture.sh` based on
  `diagnose-scrutiny.sh --capture-startup` so failed TrueNAS Custom Apps can
  preserve startup logs before middleware cleanup removes their containers.

### P2 — migrate diagnostics without behavior change

- [ ] migrate `diagnose-influxdb.sh` first as the smallest reference;
- [ ] migrate `diagnose-wazuh.sh`;
- [ ] migrate `diagnose-scrutiny.sh`;
- [ ] migrate `diagnose-sentry.sh` last because Kafka topics/groups,
  heartbeat files and one-shot migrations are specialized;
- [ ] keep current CLI paths as compatibility wrappers during the migration;
- [ ] preserve the global `audit-app-lifecycle.sh` as the orchestrator and
  remove duplicate service-specific probing from it.

### P3 — service contracts + thin adapters

- [ ] add declarative contracts under `scripts/contracts/truenas/` for
  app id, required containers, endpoints/status codes, dependencies, mounts,
  networks, secret contracts and stabilization windows;
- [ ] add generic `scripts/truenas/diagnose-service.sh <service>`;
- [ ] keep thin specialized adapters only where domain semantics require them:
  Sentry Kafka, Scrutiny SMART/InfluxDB migrations, Wazuh TLS ownership,
  InfluxDB scraper/token details and Talos/Kubernetes resource semantics;
- [ ] allow the global TrueNAS audit and later FastAPI topology/health APIs to
  consume the same contract/result model.

### P4 — reorganize `scripts/` safely

- [ ] split TrueNAS implementations into `diagnose/`, `bootstrap/`,
  `deploy/` and `recover/`;
- [ ] preserve old paths as wrappers for at least one release cycle so docs,
  CI and operator habits do not break;
- [ ] add quality gates for shebang/executable mode, `bash -n`/ShellCheck and
  discourage new duplicated runtime primitives outside `scripts/lib/`.

### Scrutiny authorization follow-up

- [x] implement the Scrutiny v0.9.3 migration-capable token contract: scope v2
  grants read access to the `nabla` org plus organization-scoped read/write
  for buckets and tasks, which is the minimum InfluxDB resource scope that can
  create/delete/rename temporary `*_new` buckets and recreate missing tasks.
  The bootstrap validates the returned authorization, writes the replacement
  secret atomically, records the scope version/auth ID and revokes superseded
  Scrutiny authorizations when possible.
- [x] runtime token rotation accepted on 2026-09-09: legacy authorization
  `114da3d49d117000` revoked, replacement authorization installed,
  `.env.secrets` mode `0600`, `token=VALID scope=v2`, and the Scrutiny
  cutover preflight reports InfluxDB=RUNNING, SMART=VISIBLE and target=MISSING.
- [ ] runtime acceptance: the reviewed fresh cutover is now in progress with
  `SCRUTINY_RESET_SQLITE=1`. Require TrueNAS `RUNNING`, web/API health,
  SMART visibility on the TrueNAS collector, a fresh workstation
  `verify-scrutiny-workstation-collector.sh --submit`, then
  `verify-scrutiny-collectors.sh` proving both `host_id=truenas` and
  `host_id=albandrieu` are present in `/api/summary` with fresh SMART
  timestamps before marking Scrutiny complete.
- [ ] workstation collector compatibility: replace the currently running
  `dev-0.8.2` / floating `master-collector` runtime with pinned
  `ghcr.io/analogj/scrutiny:v0.9.3-collector`. The v0.8.2 registration model
  does not send `scrutiny_uuid`, so the v0.9.3 server filters those devices.
  The workstation verifier now fails on version mismatch and, after
  `--submit`, requires both actual SMART collection and
  `host_id=albandrieu` visibility in `/api/summary`.
