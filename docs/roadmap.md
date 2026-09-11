# Homelab roadmap

Last updated: 2026-09-11.

This file is the concise operational index. Detailed design, incident evidence and rollback procedures stay in the specialized documents:

- [Homelab ordered reboot runbook](./homelab-reboot-runbook.md)
- [TrueNAS reboot incident · 2026-09-11](./truenas-reboot-incident-20260911.md)
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
- [x] PR #191 introduces a manifest-aware, idempotent reboot resume reconciler and starts operator-script consolidation.
- [ ] TrueNAS LXC GitHub Actions runner remains planned/dormant; prefer an unprivileged Ubuntu 24.04 LTS LXC plus remote builder for trusted workloads.

## P0 — finish the current controlled TrueNAS reboot

Do not start Vault, Falco, Kubara bootstrap, new service migrations or broad cleanup until this transaction is fully accepted.

1. [x] Preserve/restore the original persistent prepare manifest after the accidental second prepare.
2. [x] Reach the prepare boundary: all TrueNAS Apps stopped, Docker empty, Talos workers then control plane stopped, VMs `STOPPED`, `phase=PREPARED`.
3. [x] Remove the historical CSI orphan after quiesce and verify the dataset is absent.
4. [x] Reboot TrueNAS through the supported TrueNAS path; boot ID changed.
5. [x] Run `--post-reboot-check`: TrueNAS ready, Docker/IPAM/br0/observer network valid, Talos APIs reachable and Kubernetes 3/3 Ready.
6. [x] Run one fresh post-reboot CSI regression: provisioning, publishContext, cross-worker RWX and reclaim are green.
7. [ ] Complete `--resume` from the saved original manifest. The old resume implementation has already shown two stop-the-world acceptance defects:
   - `code` eventually became healthy but its slow package provisioning exceeded the old RUNNING acceptance window;
   - `graylog` remains `DEPLOYING` while later Apps are still `STOPPED`.
8. [ ] Diagnose/recover Graylog dependency ordering before treating the remaining STOPPED Apps as individual failures. Graylog requires Mongo and OpenSearch Security; the lifecycle planner must map those relations to concrete TrueNAS App IDs and start backend waves first.
9. [ ] Run `--verify`, cluster/network gates, Docker IPAM audit, platform diagnostics and orphan-shim check.
10. [ ] Only then start bounded P5 cleanup and unlock P1/P2 work.

## P0.1 — reboot lifecycle hardening

- [x] Normalize TrueNAS `system.ready` representation.
- [x] Persist `PREPARING` / `PREPARED`; support `--continue-prepare`; refuse a second same-boot transaction.
- [x] Validate immutable manifest/bundle identity and checksums.
- [x] Add targeted Docker/containerd orphan-shim diagnostics/recovery.
- [x] Add `scripts/truenas/reconcile-reboot-resume.sh` in PR #191: idempotent resume, separate middleware/job/readiness timeouts, per-App overrides, bounded runtime/log diagnostics and wave-level error aggregation.
- [ ] After the live transaction closes, make `reboot-homelab.sh --resume` delegate to the reconciler and delete the duplicate resume/wait/diagnostic implementation.
- [ ] Add a fixture that simulates an interrupted prepare after earlier Apps were stopped and proves continuation never regenerates the frozen manifest/plans.
- [ ] Add a Docker fixture for `Running=true`, `Pid=0`, exactly-one-shim recovery and refusal when `Pid>0`.
- [ ] Make `runtime.appId` canonical for every TrueNAS-backed `x-nabla` service. Prioritize Graylog, Mongo and OpenSearch Security so `dependsOn` / `storesIn` become real lifecycle wave barriers.
- [ ] Add a lifecycle fixture asserting Graylog cannot be scheduled before Mongo and OpenSearch Security are accepted RUNNING.
- [ ] Reduce the remaining `no topology mapping` set to zero or an explicit reviewed allowlist.
- [ ] Keep current + previous known-good reboot bundles until another normal reboot cycle passes.

## P0.2 — CSI hardening

- [x] Dynamic provisioning, controller publishContext, cross-worker RWX and fresh reclaim are green.
- [ ] Make `smoke-truenas-csi-nfs.sh` directly verify bounded TrueNAS NFS share and ZFS dataset disappearance after Kubernetes reclaim.
- [ ] Treat TrueNAS API success as insufficient unless the resource postcondition is also satisfied, especially for NAS-143316.
- [ ] Keep read-only validation separate from write/admin CSI credentials where possible.
- [ ] Harden smoke Pods toward Restricted PSS: `allowPrivilegeEscalation=false`, drop `ALL`, `runAsNonRoot=true`, seccomp `RuntimeDefault`.
- [ ] Evaluate TrueNAS CSI `v1.0.3 -> v1.3.0` only after the reboot baseline is stable.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27.

## P1 — infrastructure secrets

Start after P0 acceptance.

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
- [ ] Sentry: complete stable consumer heartbeat/Kafka-group acceptance and synthetic event proof.
- [ ] Scrutiny: finish TrueNAS SMART acceptance plus workstation collector with pinned v0.9.3 collector.
- [ ] AutoKuma TrueNAS registration.
- [ ] Akvorado ingestion/query acceptance.
- [ ] ntopng / Suricata reconciliation.
- [ ] Pi-hole post-reboot functional acceptance: DNS, UI/API, `pihole-dns-sync`, exporter, no restart loop.
- [ ] Build a derived immutable code-server image with required packages/extensions baked in; remove apt/package installation from the reboot/startup critical path.
- [ ] OpenRAG Docling ingestion, then OpenRAG ↔ workstation LiteLLM/GPU route. Sentry completion remains ahead of this work.

## P3.1 — FastAPI homelab observer

Keep FastAPI as an observer, not an appliance recovery controller.

- [ ] Prove TrueNAS, pfSense, Cloudflare, Prometheus, Sentry and Pyroscope transport/auth/application results independently.
- [ ] Keep Cloudflare API uncertainty as warning-only when global status cannot be confirmed.
- [ ] Continue least-privilege `fastapi_observer` A/B validation.
- [ ] Keep expensive fan-out probes bounded, cached and staggered.
- [ ] Prefer Prometheus runtime evidence where metrics exist while retaining TrueNAS App state and direct HTTP/HTTPS/TCP probes as independent evidence.

## P4 — identity and policy

- [ ] Keycloak/GitHub SSO after network/storage stability.
- [ ] Vault/OpenBao human authentication after infrastructure secrets.
- [ ] Continue NIST CSF 2.0 mapping.
- [ ] Move normal Kubernetes workloads toward Restricted Pod Security; retain explicit privileged exceptions only for infrastructure components that require them.

## P5 — bounded post-reboot cleanup

Entry condition: `--verify` is green and P0 is closed.

- [ ] Archive reboot manifest, boot IDs, source SHA and incident evidence.
- [ ] Confirm no disposable CSI namespace/PVC/PV/VolumeAttachment/share/dataset remains.
- [ ] Inventory legacy Docker `172.16.x.0/24` networks with owner/endpoint evidence; never use `docker network prune`.
- [ ] Protect `intranet`, `traefik_network`, `sample-observer`, `nabla-security` and `secrets-backend`.
- [ ] Remove only reviewed zero-endpoint stale networks through their canonical owner lifecycle.
- [ ] Keep pre-existing CRASHED Apps as separately tracked debt, not reboot regressions.
- [ ] Re-run orphan-shim diagnostics after Apps settle.

## Accepted code/debt reduction plan

The objective is a net reduction of imperative Bash, duplicate lifecycle logic and duplicated documentation, while preserving stable operator entry points for at least one release cycle.

1. [ ] **One resume implementation.** `reboot-homelab.sh --resume` delegates to `reconcile-reboot-resume.sh --apply`; remove the duplicate wave/wait/diagnostic code from the reboot orchestrator.
2. [ ] **`scripts/lib/truenas.sh`.** Centralize bounded middleware calls, normalized readiness, App state, lifecycle waits and persistent reboot-manifest helpers.
3. [ ] **`scripts/lib/docker.sh`.** Centralize container state/health/PID/restarts/exit, Compose-project selection and orphan-shim correlation.
4. [ ] **`scripts/lib/diagnostic.sh`.** Centralize compact/full output, ok/warn/fail/skipped counters and stable exit codes.
5. [ ] **`scripts/lib/probe.sh`.** One bounded HTTP/HTTPS/TCP/DNS probe implementation with retry semantics.
6. [ ] **`scripts/lib/secrets.sh`.** Centralize owner/mode/key-presence checks without secret disclosure.
7. [ ] **Data over Bash policy.** Move lifecycle/readiness policy into canonical `x-nabla`/catalog metadata: `runtime.appId`, startup timeout, readiness type/target, dependency relations, slow-start behavior and criticality.
8. [ ] **Prebuilt code-server image.** Bake packages/extensions into an immutable derived image; remove startup-time package provisioning.
9. [ ] **Incident fixtures.** Cover interrupted prepare/continue, Docker ghost shim and lifecycle ordering (including Graylog after Mongo/OpenSearch Security).
10. [ ] **Keep roadmap concise.** Roadmap = status/next action; runbooks = procedure; incident docs = evidence. Link instead of copying command blocks.
11. [ ] **Anti-duplication quality gate.** Once primitives are migrated, reject redefinitions of middleware/App-state/diagnostic/probe helpers in service scripts.

## Target operator-script architecture

```text
scripts/
├── lib/
│   ├── common.sh       # generic shell primitives
│   ├── diagnostic.sh   # output, counters, stable exit codes
│   ├── truenas.sh      # middleware, Apps, lifecycle, manifests
│   ├── docker.sh       # container/runtime/containerd evidence
│   ├── probe.sh        # HTTP/HTTPS/TCP/DNS probes
│   └── secrets.sh      # ownership/mode/presence, never secret values
├── truenas/
│   ├── reboot-homelab.sh          # orchestration only
│   ├── reconcile-reboot-resume.sh # post-reboot lifecycle reconciliation
│   ├── diagnose-platform.sh       # composition of diagnostics
│   └── ...                         # stable operator wrappers
└── talos/
```

Quality gates must cover shebang/executable mode, `bash -n`, ShellCheck, contract tests and duplicate runtime primitives. Existing operator paths remain wrappers for at least one release cycle.

## Ordering rule

Until P0 closes:

```text
finish App resume / dependency ordering
  -> --verify + platform gates
  -> close P0
  -> lifecycle/topology + script-debt consolidation
  -> CSI hardening postconditions/PSS
  -> infrastructure secrets
  -> Vault / Falco / Kubara
  -> Kubernetes ingress + test.albandrieu.com
  -> Sentry / Scrutiny / remaining service work
  -> Docling / OpenRAG-LiteLLM
  -> bounded P5 cleanup
```
