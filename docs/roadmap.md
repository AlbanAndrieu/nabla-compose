# Homelab roadmap

Last updated: 2026-09-11.

This file is the concise operational index. Detailed design and rollback notes
remain in the specialized documents:

- [Homelab ordered reboot runbook](./homelab-reboot-runbook.md)
- [TrueNAS CSI orphan datasets](./truenas-csi-orphan-datasets.md)
- [TrueNAS Docker IPAM roadmap](./truenas-docker-ipam-roadmap.md)
- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)
- [Kubernetes platform tools · Vault, Falco and Kubara](./kubernetes-platform-tools.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)

## Current platform state

- [x] Talos control plane `172.17.0.50` and workers `172.17.0.51` /
  `172.17.0.52` are Kubernetes `Ready`.
- [x] Talos `v1.13.9`, Kubernetes `v1.36.3`, etcd single member healthy and no
  node pressure.
- [x] CoreDNS, kube-proxy and Talos-managed Flannel are operational.
- [x] Persistent operator tooling is installed outside TrueNAS package
  management: `kubectl`, `talosctl`, Helm and Kubara.
- [x] Talos VM steady-state policy is reconciled with `autostart=true` and
  graceful shutdown timeout `180s`.
- [x] TrueNAS Docker target IPAM is configured as `10.200.0.0/16` with `/24`
  allocations; the protected `sample-observer=10.254.255.0/28` network is
  intact.
- [x] PR #187 restored the TrueNAS CSI controller-publish path:
  `attachRequired=true`, `csi-attacher`, VolumeAttachment RBAC and NFS
  publishContext.
- [x] Fresh TrueNAS CSI RWX acceptance is green: dynamic PVC/PV, attached
  VolumeAttachment, NFS publishContext, worker-A write, worker-B read, namespace
  cleanup, PV reclaim, NFS share removal and actual fresh ZFS dataset removal.
- [ ] Historical CSI dataset
  `cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530` is separately
  tracked as an orphan: no PV, no VolumeAttachment, no NFS reference, no
  snapshots/children, but `zfs.resource.destroy` returns `EBUSY`. Do not use
  `zfs destroy -f`.
- [x] `scripts/truenas/diagnose-csi-orphans.sh --check` inventories dynamic
  `pvc-*` datasets and distinguishes referenced, orphan and candidate states.
- [x] The CSI orphan documentation records that a real ZFS dataset may be absent
  from the TrueNAS Storage UI; ZFS/middleware evidence is authoritative.
- [x] TrueNAS 26 dataset deletion false-success behavior is tracked against
  upstream NAS-143316; cleanup acceptance is based on postconditions, not a
  successful high-level return value.
- [x] TrueNAS `midclt call system.ready` on this host can render `True`.
  Reboot orchestration now normalizes boolean case rather than comparing
  literally with lowercase `true`.
- [x] A partial reboot prepare failure exposed the need for a persistent prepare
  state machine. `reboot-homelab.sh` now writes `PREPARING` before mutation,
  refuses a second fresh prepare on the same boot, and supports
  `--continue-prepare`.
- [x] Pi-hole stop failure root cause identified: `pihole-dns-sync` was in a
  Docker ghost state with `Running=true`, `Restarting=true`, `.State.Pid=0` and
  an orphaned `containerd-shim-runc-v2`.
- [x] Targeted Pi-hole runtime recovery succeeded without restarting
  Docker/containerd globally: restart policy disabled for the exact container,
  exact orphan shim terminated, Docker state converged, then
  `midclt call -j app.stop pihole` reached `STOPPED`.
- [x] `scripts/truenas/diagnose-docker-orphan-shims.sh --check` detects the
  `Running/Restarting + Pid=0` ghost-state pattern.
- [x] `scripts/truenas/diagnose-docker-orphan-shims.sh --recover <container>`
  provides guarded single-container recovery and refuses to touch a live
  container PID.
- [x] Standard TrueNAS platform diagnostics include App lifecycle,
  Docker/containerd orphan-shim inventory, Talos/Kubernetes posture and CSI
  dataset/orphan inventory.

## P0 — finish the current controlled TrueNAS reboot

Do not start Vault, Falco, Kubara bootstrap, new service migrations or broad
cleanup until this transaction is complete.

The strict order is:

1. [ ] **Continue the existing prepare transaction** using the original
   persistent manifest. The failed first prepare already stopped several Apps;
   do not run a fresh `--prepare`.
2. [ ] Run `reboot-homelab.sh --continue-prepare` and require all remaining
   Apps to reach `STOPPED`, `docker ps` to be empty, Talos workers to shut down
   before the control plane, all three VMs to reach `STOPPED`, and
   `phase=PREPARED`.
3. [ ] **Retry the historical CSI orphan after real quiesce** with supported
   `zfs.resource.destroy`. If it still returns `EBUSY`, preserve evidence and do
   not force deletion.
4. [ ] Reboot TrueNAS only through the supported TrueNAS UI/API after
   `phase=PREPARED`.
5. [ ] Run `reboot-homelab.sh --post-reboot-check` and require:
   changed boot ID, normalized `system.ready`, Docker middleware/systemd healthy,
   IPAM persisted, `br0=172.17.0.24/24`, protected observer network intact,
   Talos VMs autostarted, all Talos APIs reachable and Kubernetes 3/3 Ready.
6. [ ] If the historical CSI orphan survived, retry its supported deletion
   post-reboot before creating new smoke resources.
7. [ ] Run one **fresh post-reboot CSI regression** and verify dynamic
   provisioning, publishContext, cross-worker RWX and TrueNAS-side share/dataset
   reclaim.
8. [ ] Run `--resume` from the saved manifest only. The reviewed explicit
   maintenance set remains `crowdsec sample`; do not resume every stopped App.
9. [ ] Run `--verify`, cluster/network gates, Docker IPAM audit and
   orphan-shim diagnostic.
10. [ ] Only then start bounded P5 cleanup.

### Current reboot incident evidence

The current prepare transaction demonstrated two important failure modes that
are now permanent requirements:

- **CLI boolean representation is not an API semantic.** A healthy
  `system.state=READY` was initially rejected because `midclt` printed `True`
  and the script compared it with lowercase `true`.
- **Prepare is not atomic.** A later App can fail after earlier Apps were
  already stopped. The original manifest and resume plan must therefore survive
  and be resumable; a second fresh snapshot is unsafe.

The Pi-hole failure also proved that
`tried to kill container, but did not receive an exit event` does not
necessarily mean a live workload is stuck. Always compare Docker's
`Running/Restarting` flags with `.State.Pid` and the exact containerd shim.

## P0.1 — reboot lifecycle hardening after the transaction

- [x] Normalize all TrueNAS `system.ready` gates.
- [x] Add `PREPARING` and `--continue-prepare`.
- [x] Refuse a same-boot fresh `--prepare` when an incomplete manifest exists.
- [x] Validate required manifest files before continuation.
- [x] Preserve legacy interrupted manifests with no phase only when boot ID and
  plan files are intact.
- [x] Add failed-App runtime evidence to the reboot script.
- [x] Add guarded Docker/containerd orphan-shim diagnostics and recovery.
- [ ] Add a fixture/integration test that simulates an App stop failure after
  some earlier Apps have stopped and proves `--continue-prepare` does not
  regenerate `apps-before.json` or `resume-plan.json`.
- [ ] Add a Docker fixture test for `Running=true`, `Pid=0`, exactly-one-shim
  recovery and refusal when `Pid>0`.
- [ ] Persist an explicit incident/evidence note in the reboot manifest when
  `--continue-prepare` is used.
- [ ] Reduce the large `no topology mapping` warning set by mapping remaining
  TrueNAS App IDs to canonical `x-nabla` service runtime ownership.
- [ ] Keep the current bundle plus at least one previous known-good rollback
  bundle until a complete reboot cycle is accepted.

## P0.2 — CSI hardening after reboot

- [x] Dynamic provisioning and controller publishContext path are green.
- [x] Cross-worker NFS RWX smoke is green.
- [x] Fresh reclaim was verified on the TrueNAS side.
- [ ] Make `smoke-truenas-csi-nfs.sh` itself verify bounded TrueNAS-side NFS
  share and ZFS dataset disappearance after Kubernetes reclaim.
- [ ] Treat TrueNAS API success as insufficient when the resource postcondition
  is still present, specifically for NAS-143316.
- [ ] Keep read-only validation independent from write/admin CSI credentials
  where possible.
- [ ] Harden smoke Pods toward Restricted-compatible security context:
  `allowPrivilegeEscalation=false`, drop `ALL`, `runAsNonRoot=true`, seccomp
  `RuntimeDefault`, while retaining BusyBox compatibility.
- [ ] Evaluate TrueNAS CSI `v1.0.3 -> v1.3.0` only after the reboot baseline is
  stable; do not upgrade during this transaction.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27.

## P1 — infrastructure secrets

Start only after the reboot and post-reboot CSI regression are accepted.

1. [ ] OpenTofu/Terragrunt and Garage backend credentials.
2. [ ] Dedicated TrueNAS infrastructure automation credential; never reuse the
   FastAPI observer identity.
3. [ ] Nexus automation credentials.
4. [ ] Talos/Kubernetes/CSI machine credentials.
5. [ ] Root-owned `0600` runtime rendering.
6. [ ] Retain encrypted recovery material.
7. [ ] Move long-lived machine secrets to Vault/OpenBao only after storage
   persistence and rollback are proven.

## P2 — platform/security tools

- [ ] Vault: keep blocked until CSI post-reboot acceptance is green.
- [ ] Falco: kernel preflight is ready; install only after the infrastructure
  baseline stops changing.
- [ ] Kubara: CLI is ready; create/review `config.yaml` before bootstrap.
- [ ] Traefik/Kubara ingress: choose an explicit bare-metal exposure model;
  do not assume a cloud LoadBalancer.
- [ ] FastAPI Kubernetes smoke: deploy an immutable image and prove
  `test.albandrieu.com` only after storage and ingress ownership are stable.

## P3 — runtime/services

- [x] Prometheus core runtime.
- [x] Grafana runtime.
- [x] Graylog runtime.
- [x] CrowdSec runtime/maintenance resume intent.
- [x] Langflow runtime.
- [x] Wazuh manager/indexer/dashboard core acceptance.
- [x] OpenRAG core runtime; Docling ingestion remains pending.
- [ ] Sentry: complete stable consumer heartbeat/Kafka-group acceptance and
  synthetic event proof; avoid whole-stack redeploy for isolated consumers.
- [ ] Scrutiny: finish TrueNAS SMART acceptance plus workstation collector using
  the pinned v0.9.3 collector.
- [ ] AutoKuma TrueNAS registration.
- [ ] Akvorado ingestion/query acceptance.
- [ ] ntopng / Suricata reconciliation.
- [ ] Pi-hole post-reboot functional acceptance:
  DNS, UI/API, `pihole-dns-sync`, exporter and restart-loop absence.
- [ ] OpenRAG Docling ingestion, then OpenRAG ↔ workstation LiteLLM/GPU route.

## P3.1 — FastAPI homelab observer

Keep FastAPI as an observer, not an appliance recovery controller.

- [ ] Prove TrueNAS, pfSense, Cloudflare, Prometheus, Sentry and Pyroscope
  transport/auth/application results independently.
- [ ] Keep Cloudflare API uncertainty as a warning when the API cannot be
  confirmed; do not mark an otherwise healthy service down solely because the
  Cloudflare observer timed out.
- [ ] Continue the dedicated `fastapi_observer` least-privilege A/B validation
  before switching the cloud runtime away from the current human/admin
  credential.
- [ ] Keep expensive fan-out probes bounded, cached and staggered.
- [ ] Prefer Prometheus runtime evidence where metrics exist, while retaining
  TrueNAS App state and direct HTTP/HTTPS/TCP probes as independent evidence.

## P4 — identity and policy

- [ ] Keycloak/GitHub SSO after network/storage stability.
- [ ] Vault/OpenBao human authentication after infrastructure secrets.
- [ ] Continue NIST CSF 2.0 mapping across Govern, Identify, Protect, Detect,
  Respond and Recover.
- [ ] Keep Kubernetes normal workloads moving toward Restricted Pod Security;
  retain explicit privileged exceptions only for infrastructure components that
  require them.

## P5 — post-reboot cleanup

Entry condition: reboot `--verify` and fresh CSI regression are both green.

- [ ] Archive reboot manifest, boot IDs, source SHA and incident evidence.
- [ ] Keep current + previous reboot bundles until another normal reboot passes.
- [ ] Confirm no disposable CSI namespace/PVC/PV/VolumeAttachment/share/dataset
  remains.
- [ ] Inventory legacy Docker `172.16.x.0/24` networks with owner and endpoint
  evidence.
- [ ] Never use `docker network prune`.
- [ ] Protect `intranet`, `traefik_network`, `sample-observer`,
  `nabla-security` and `secrets-backend`.
- [ ] Remove only reviewed zero-endpoint stale networks through their canonical
  owner lifecycle.
- [ ] Keep pre-existing `CRASHED` Apps as separately tracked debt; do not
  relabel them as reboot regressions.
- [ ] Re-run `scripts/truenas/diagnose-docker-orphan-shims.sh --check` after
  Apps settle and investigate any new `Pid=0` ghost state.

## Script architecture refactor

After the reboot transaction, continue the operator-script consolidation:

- [ ] `scripts/lib/common.sh`: root/operator checks, required commands, temp
  files and traps.
- [ ] `scripts/lib/diagnostic.sh`: ok/fail/warn/skipped counters, compact/full
  output and stable exit codes.
- [ ] `scripts/lib/truenas.sh`: bounded middleware calls, App state, lifecycle
  waits and persistent reboot-manifest helpers.
- [ ] `scripts/lib/docker.sh`: container state, health, restart count,
  mounts/networks and orphan-shim correlation.
- [ ] `scripts/lib/probe.sh`: HTTP/HTTPS/TCP/DNS probes with bounded retry.
- [ ] `scripts/lib/secrets.sh`: owner/mode/key-presence checks without secret
  disclosure.
- [ ] Preserve current operator paths as wrappers for at least one release cycle.
- [ ] Add quality gates for shebang/executable mode, `bash -n`, ShellCheck and
  duplicate runtime primitives.

## Ordering rule

The immediate controlled reboot is the only P0 transaction. Do not interleave
new platform mutations with it.

After reboot acceptance:

```text
CSI regression
  -> infrastructure secrets
  -> Vault / Falco / Kubara
  -> Kubernetes ingress + test.albandrieu.com
  -> remaining service migrations
  -> bounded cleanup / architecture refactor
```

Sentry completion remains ahead of Docling/OpenRAG-LiteLLM. Scrutiny and other
service-specific work may proceed only after the reboot baseline is stable.
