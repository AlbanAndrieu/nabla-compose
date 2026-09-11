# TrueNAS Docker IPAM and network migration roadmap

Last updated: 2026-09-11.

This roadmap tracks the post-reboot Docker/Apps network migration on TrueNAS.
The canonical network/IPAM map is documented in
[`homelab-network-topology.md`](./homelab-network-topology.md), and the controlled
host lifecycle is documented in
[`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md).

The migration is intentionally staged: the global default pool is already moved
to `10.200.0.0/16`, while existing `172.16.x.0/24` networks are retained until
their owners and live consumers are proven. Application recovery, CSI/storage
acceptance, legacy-network cleanup and reboot persistence are separate gates.
Cleanup is deliberately post-reboot work: it starts only after the ordered
reboot reaches a successful `--verify` gate.

## Current evidence

- TrueNAS Apps pool: `cpool`; dataset: `cpool/ix-apps`.
- The 2026-09-11 reboot initially left middleware `docker.status=FAILED` even
  though Docker 29.0.4 eventually became active and restored historical network
  state.
- The old default IPv4 pool was reported as
  `base=172.17.0.0/12,size=24`, effectively `172.16.0.0/12`; it overlapped the
  physical homelab LAN `172.17.0.0/24`.
- The selected replacement `10.200.0.0/16,size=24` is disjoint from the
  inventoried pfSense, TrueNAS, workstation, Talos and FastAPI observer routes.
- `scripts/truenas/migrate-docker-address-pool.sh --apply` completed through
  TrueNAS `docker.update`, retained IPv6 `fdd0::/48,size=64`, and converged
  `docker.service=active` plus middleware `docker.status=RUNNING`.
- A disposable default-IPAM smoke network received `10.200.1.0/24`; subsequent
  real application networks also allocated inside `10.200.x.0/24`.
- The 03:37 network audit reported 49 `legacy-empty`, 0 `legacy-active`, 5
  `protected-shared` and 9 `target-pool` networks. No network was removed.
- The same audit preserved `intranet`, `traefik_network`, `sample-observer`,
  `nabla-security` and `secrets-backend` as protected shared contracts.
- Many Apps were then manually stopped for maintenance/time reduction. A later
  snapshot reported 33 `CRASHED`, 9 `DEPLOYING`, 5 `RUNNING` and 49 `STOPPED`;
  therefore current `STOPPED` state alone is not evidence of intended
  steady-state disablement.
- Comparing the pre-stop and maintenance snapshots with the safe rule
  `RUNNING|DEPLOYING -> STOPPED` selects only `crowdsec` and `sample` for
  automatic reboot resume. Apps that were already `CRASHED` before being stopped
  remain excluded from the reboot resume set and require separate diagnosis.
- The first idempotent IPAM re-check exposed an IPv4/IPv6 comparison defect when
  Docker's `fdd0::/64` network was compared with `10.200.0.0/16`; the helper now
  filters address families before overlap/subnet tests.
- A subsequent live IPAM check passed fully: `docker.config` remained
  `10.200.0.0/16,size=24`, Docker middleware/systemd were `RUNNING`/active,
  `br0=172.17.0.24/24`, `sample-observer=10.254.255.0/28`, and the default bridge
  stayed inside `10.200.0.0/16`.
- Live Talos VM policy reconciliation completed on all three VMs: `taloscp01`,
  `taloswk01` and `taloswk02` now report `autostart=true`,
  `shutdown_timeout=180`, and `RUNNING`.
- The first ordered reboot preflight proved all three Kubernetes nodes `Ready`
  but failed on the first Talos API probe to target `172.17.0.50`. The original
  helper relied on the operator talosconfig endpoint list and discarded Talos
  stderr, so that result did not distinguish endpoint, mTLS, RPC or transport
  failure. The helper now routes all node operations through explicit control
  endpoint `172.17.0.50`, keeps `--nodes` as the target selector, and prints the
  underlying client error. The preflight must be rerun before `--prepare`.
- TrueNAS CSI PR #187 restored the required controller-publish path for
  TrueNAS CSI v1.0.3: `CSIDriver.spec.attachRequired=true`, `csi-attacher`, and
  least-privilege VolumeAttachment read/patch/status RBAC. The retained smoke is
  deliberately still present while runtime evidence is collected.
- Current retained CSI evidence is stronger than the former failure: PVC
  `nabla-csi-rwx` is `Bound`, PV
  `pvc-03741395-a00a-4eaf-a04e-da10e08ec530` exists, and Kubernetes now creates
  a `VolumeAttachment` for `talos-7fc-fdt`. It is still `attached=false`.
- The CSI controller rollout currently has two generations. An old controller
  Pod without `csi-attacher` is still present/pending termination while the new
  generation is expected to contain the attacher. Logs selected through
  `deployment/truenas-csi-controller` can therefore select the old Pod and are
  not sufficient evidence. The exact new Pod must be identified and inspected
  by Pod name before the planned reboot.
- `sample-observer=10.254.255.0/28` remains outside both Docker default pools;
  FastAPI observer source `10.254.255.9/32` remains the TrueNAS allowlist
  contract.

## Current routed/IPAM map

```text
pfSense WAN           82.66.4.0/24       pfSense=82.66.4.247, gateway=82.66.4.254
homelab LAN           172.17.0.0/24      pfSense=.1, TrueNAS=.24, Talos=.50-.52, workstation=.57
pfSense VLAN          10.20.0.0/24       pfSense=10.20.0.1
pfSense host address  10.10.10.1/32
workstation LXC       10.0.3.0/24
workstation libvirt   192.168.39.0/24, 192.168.122.0/24
sample-observer       10.254.255.0/28     gateway=.1, FastAPI observer=.9
TrueNAS Docker        10.200.0.0/16      current default /24 allocations
legacy TrueNAS Docker 172.16.x.0/24      retained pending owner migration
```

## P0 — evidence and safety contracts

- [x] Capture `docker.config`, `docker.status`, `docker info`, Docker network
  inventory, routes and TrueNAS application inventory before apply.
- [x] Inventory physical/VLAN/routed CIDRs from pfSense, TrueNAS and workstation.
- [x] Preserve the previous `address_pools`/`cidr_v6` rollback payload.
- [x] Add `scripts/truenas/audit-docker-network-migration.sh --check` to classify
  target-pool, protected-shared, legacy-active, legacy-empty, builtin and other
  networks without modifying Docker.
- [x] Protect shared networks `intranet`, `traefik_network`, `sample-observer`,
  `nabla-security`, and `secrets-backend` from generic migration cleanup.
- [x] Add a persistent reboot manifest under `/mnt/cpool/var/nabla/reboot` and a
  persistent reviewed execution bundle under `/mnt/cpool/tools/nabla-reboot` so
  pre/post-reboot orchestration does not depend on `/tmp` or a moving branch.
- [ ] Preserve a normal TrueNAS configuration/database backup outside `/tmp`
  before the reboot acceptance gate.
- [ ] Complete repository-wide review of explicit `ipv4_address`, subnet,
  gateway, firewall/source allowlist and DNS dependencies referencing legacy
  `172.16.x.0/24` networks before renumbering a protected shared network.

## P1 — global default address-pool migration

- [x] Select `10.200.0.0/16` with `/24` Docker allocations.
- [x] Apply through supported TrueNAS `docker.update`; do not edit daemon files.
- [x] Preserve IPv6 `fdd0::/48,size=64` and `cidr_v6=fdd0::/64`.
- [x] Prove live convergence with `docker.service=active`,
  `docker.status=RUNNING`, persisted `docker.config.address_pools`, and a
  disposable allocation inside `10.200.0.0/16`.
- [x] Make the migration helper idempotent after the target pool is active,
  including explicit IPv4/IPv6 address-family filtering.
- [x] Add a dedicated `--post-reboot-check` mode that never reapplies the pool
  and fails if the configured IPv4 pool drifted back to the old value.
- [ ] **Post-reboot persistence gate:** require `10.200.0.0/16,size=24`,
  `docker.service=active`, middleware `RUNNING`, `br0=172.17.0.24/24`, protected
  `sample-observer=10.254.255.0/28` when present, and Docker's default bridge
  still inside `10.200.0.0/16`.
- [ ] If the pool reverts after reboot, capture middleware/datastore/boot
  evidence before any new `--apply`; do not hide recurrence by immediately
  rewriting the setting.

## P2 — application and legacy-network convergence

- [x] Re-run the read-only classifier after migration: 49 empty legacy candidates,
  0 active legacy candidates, 5 protected shared networks and 9 target-pool
  networks were observed; no cleanup was performed.
- [x] Bound middleware calls in `reconcile-apps-after-ipam.sh` and make
  `app.get_instance` network-detail expansion best-effort so a slow middleware
  response does not turn a read-only check into a false failure.
- [x] Review the maintenance-stopped App set using the pre-stop snapshot: only
  `crowdsec` and `sample` were healthy/active (`RUNNING`) before becoming
  `STOPPED`. Previously `CRASHED` Apps remain outside automatic reboot resume.
- [ ] For each app-owned legacy network, prefer an owner-specific lifecycle
  operation so Compose/TrueNAS recreates its own network under the new allocator.
- [ ] Keep intentionally stopped Apps stopped; their empty project-owned legacy
  network can be migrated when that App is deliberately started.
- [ ] A legacy network with live endpoints is never removed merely to force
  renumbering. Migrate its owner/consumers first.
- [ ] Remove orphan network/sandbox artifacts only in explicit bounded batches,
  with before/after counts and daemon logs. Never use blanket
  `docker network prune`.
- [ ] Acceptance: expected-running Apps are `RUNNING`; intentionally stopped Apps
  remain `STOPPED`; no required external/shared network was removed; new
  app-owned default bridges allocate from `10.200.0.0/16`.

## P3 — CSI/storage gate and ordered TrueNAS reboot

### P3.1 — close the retained CSI evidence before the planned reboot

A normal planned reboot must not be used as a workaround for the current CSI
controller rollout. Rebooting while the retained `VolumeAttachment` is
`attached=false` would erase useful evidence about whether the new attacher
actually executed `ControllerPublishVolume`.

- [ ] Identify both controller ReplicaSets/Pods and the exact **new** Pod whose
  container list includes `csi-attacher`.
- [ ] Inspect `csi-attacher` and `csi-controller` logs by exact new Pod name; do
  not use `kubectl logs deployment/...` while both generations coexist.
- [ ] Require the old controller Pod/ReplicaSet to terminate cleanly and the
  current Deployment rollout to become complete.
- [ ] Inspect retained VolumeAttachment
  `csi-2db054df7894042dbfee6309d758e9540ff5b11a2191d8316c58b3cd634a8712`
  and require:
  - `status.attached=true`;
  - `status.attachmentMetadata.protocol=nfs`;
  - non-empty `nfsServer` (expected `172.17.0.24`);
  - non-empty `nfsPath` for the retained PVC.
- [ ] Require retained writer `csi-writer` to leave `ContainerCreating` and
  become `Running` without recreating the PVC merely to hide the original
  failure.
- [ ] Complete the cross-worker RWX proof: write marker on worker A, remove the
  writer, schedule reader on worker B, read the same marker.
- [ ] Delete the disposable smoke namespace only after evidence capture; require
  PV reclaim plus automatic TrueNAS dataset/share removal.
- [ ] Run one fresh clean CSI smoke after retained-state recovery so acceptance
  is not based only on recovery of an object created under the old controller.

If an operationally mandatory host reboot must happen before those items are
complete, record CSI runtime acceptance as **deferred** and preserve all
retained object/log evidence first. A healthy post-reboot CSI smoke does not
prove what caused the pre-reboot `attached=false` state.

### P3.2 — ordered host lifecycle

- [x] Repository IaC already declares `talos_vm_autostart=true` for `taloscp01`,
  `taloswk01` and `taloswk02`.
- [x] Add declarative `talos_vm_shutdown_timeout=180` and wire it to each VM as
  the hypervisor-side graceful shutdown safety window.
- [x] Add `scripts/truenas/reconcile-talos-vm-policy.sh` to check/apply only
  `autostart=true` and `shutdown_timeout=180` on the live VMs without replacing
  disks, NICs or VMs.
- [x] Reconcile the live Talos VM policy: all three VMs now report
  `autostart=true`, `shutdown_timeout=180` and `RUNNING`.
- [x] Add `scripts/truenas/plan-app-lifecycle-order.py` to convert required
  generated topology relations into dependency-first start waves and
  reverse-dependency stop waves; required cycles fail closed.
- [x] Add `scripts/truenas/reboot-homelab.sh` and
  `docs/homelab-reboot-runbook.md` with the controlled sequence:

  ```text
  CSI retained-evidence gate
  -> Apps stop -> Talos worker drain/shutdown -> Talos control-plane shutdown
  -> operator TrueNAS reboot -> VM autostart -> Kubernetes Ready/uncordon
  -> CSI post-reboot regression gate -> saved Apps resume in dependency order
  ```

- [x] Normal reboot lifecycle uses `app.stop`/`app.start`, not `app.redeploy`, so
  it does not intentionally pull application image updates.
- [x] Preserve Apps that were already `STOPPED` unless explicitly added to the
  persistent maintenance resume set.
- [x] Harden Talos lifecycle calls to use explicit control-plane endpoint
  `172.17.0.50`, separate endpoint selection from target-node selection, and
  retain detailed Talos client errors.
- [ ] Rerun ordered reboot `--check` with the refreshed helper; review generated
  start/stop waves, unmapped Apps and `crowdsec sample` maintenance resume set.
- [ ] Run `--prepare`; require zero running Docker containers and all three Talos
  VMs `STOPPED` before authorizing the TrueNAS reboot.
- [ ] Perform one normal TrueNAS reboot.
- [ ] Run `--post-reboot-check`; require changed boot ID, TrueNAS readiness,
  persisted Docker IPAM, all three VMs `autostart=true` + `RUNNING`, all Talos
  APIs reachable and all Kubernetes nodes Ready.
- [ ] Before App resume, rerun the CSI declarative/prerequisite gate and a clean
  cross-worker TrueNAS NFS CSI smoke. A Kubernetes-Ready cluster with broken
  persistent storage is not sufficient to resume dependent Apps.
- [ ] Run `--resume` and `--verify`; only the saved resume set should return to
  `RUNNING`, while intentionally stopped Apps remain stopped.

## P4 — boot-time middleware reconciliation

- [x] The live IPAM update reconciled middleware from `docker.status=FAILED` to
  `RUNNING` without changing the Apps dataset.
- [ ] After the controlled reboot, prove middleware and systemd independently
  converge instead of relying on the aggregate Apps status alone.
- [ ] If `docker.status` returns to `FAILED`, capture the relevant `core.get_jobs`
  record and daemon boot log before any repair.
- [ ] Determine whether recurrence is a middleware timeout/race, stale network
  replay, application restart storm or another dependency before changing
  service timeouts.

## P5 — post-reboot cleanup and convergence

**Entry condition:** P3 `--post-reboot-check`, CSI post-reboot regression and
`--verify` are GREEN. Cleanup is not part of the reboot transaction and must not
be used to make a failed reboot appear healthy.

### P5.1 — archive the successful baseline

- [ ] Persist the successful reboot manifest, TrueNAS boot ID, `app.query`,
  `docker info`, `docker ps`, complete Docker network inspect, routes, relevant
  middleware/docker boot logs, Talos/Kubernetes node state and CSI acceptance
  evidence outside `/tmp`.
- [ ] Retain the exact successful orchestration bundle and at least one previous
  rollback/recovery bundle until a subsequent normal reboot is accepted.
- [ ] Add an explicit retention policy before removing older bundles/evidence;
  never remove the only known-good recovery snapshot merely to save space.

### P5.2 — remove disposable CSI smoke state only after reclaim proof

- [ ] Require no retained `nabla-csi-smoke` namespace, writer/reader Pod, PVC,
  PV or VolumeAttachment after the successful acceptance/reclaim sequence.
- [ ] Verify the corresponding TrueNAS CSI NFS share and dataset are removed by
  the normal CSI reclaim path.
- [ ] If Kubernetes objects are gone but the dataset/share remains, record it as
  a CSI orphan and diagnose controller/reclaim evidence before any manual
  deletion. Do not `zfs destroy` or delete the share as the first recovery step.
- [ ] Record any genuinely orphaned historical CSI dataset/share separately from
  the reboot and remove it only after proving no PV/PVC/VolumeAttachment or
  workload references it.

### P5.3 — converge legacy Docker networks in bounded owner-aware batches

- [ ] Rerun `scripts/truenas/audit-docker-network-migration.sh --check` after all
  intended Apps are stable.
- [ ] For every remaining `172.16.x.0/24` network record: network name/subnet,
  endpoint count, Compose/TrueNAS owner labels, external/shared semantics and
  relevant sandbox/container references.
- [ ] Never generically remove `intranet`, `traefik_network`, `sample-observer`,
  `nabla-security` or `secrets-backend`; they remain protected even with zero
  endpoints until their explicit contract is deliberately migrated.
- [ ] Remove a legacy network only when it has zero live endpoints, is not a
  required external/shared network, and its owner/reference evidence proves it
  stale or orphaned.
- [ ] Use small reviewed batches with before/after inventory and daemon logs;
  never use `docker network prune`.
- [ ] For an app-owned network, prefer the canonical owner lifecycle
  (`app.start`/reviewed Compose down-up as appropriate) so recreation allocates
  from `10.200.0.0/16`. A raw `docker network rm` without owner convergence is
  not a migration strategy because the old definition may simply recreate it.
- [ ] Correlate historical `sandbox ... not found` warnings with proven-unused
  networks/containers before removal. Never perform direct containerd metadata
  surgery solely because a stale sandbox warning exists.

### P5.4 — converge application ownership and pre-existing failures

- [ ] Compare pre-maintenance intended state, persistent resume manifest and
  post-reboot `app.query`; explain every difference.
- [ ] Keep pre-reboot `CRASHED` Apps outside the reboot success path. Diagnose
  them as independent application debt rather than converting them into a
  restart backlog.
- [ ] Identify duplicate direct-Compose versus TrueNAS-managed ownership and
  retain exactly one canonical owner only after volumes/bind mounts, networks,
  secrets and lifecycle dependencies are proven.
- [ ] Remove superseded containers/networks only after canonical replacement is
  healthy; preserve persistent datasets/bind mounts unless a separate data
  deletion decision is reviewed.

### P5.5 — final cleanup acceptance

- [ ] `docker.service=active` and TrueNAS middleware `docker.status=RUNNING` after
  cleanup, with no repair/reapply of the default address pool.
- [ ] `br0=172.17.0.24/24` and default route via `172.17.0.1` remain unchanged.
- [ ] New default Docker networks continue to allocate inside
  `10.200.0.0/16,size=24`.
- [ ] Talos remains 3/3 Ready and the clean cross-worker CSI smoke remains green.
- [ ] Expected-running Apps remain healthy; intentionally stopped Apps and
  pre-existing failed Apps remain correctly classified.
- [ ] Every surviving legacy `172.16.x` network is an explicit protected/shared
  exception or a named owner migration backlog item. No unexplained historical
  network is silently accepted.
- [ ] Every deferred cleanup/failure has a roadmap owner/reason/evidence pointer;
  there is no unrecorded remainder.

## Definition of done

The migration is complete only when all of these are true:

- [x] the overlapping default pool is replaced live by `10.200.0.0/16`;
- [ ] the same pool survives a normal TrueNAS reboot without reapplication;
- [ ] all three Talos VMs survive the reboot contract with `autostart=true` and
  Kubernetes returns all three nodes to Ready;
- [ ] TrueNAS CSI proves attach/publishContext, cross-worker RWX persistence and
  automatic reclaim before the reboot, then passes a clean regression after the
  reboot;
- [ ] expected-running Apps have recovered according to the saved topology-backed
  resume manifest;
- [ ] app-owned default networks are on the new allocator when recreated;
- [ ] any remaining `172.16.x` networks are explicit documented exceptions or
  protected shared contracts, not unexplained historical leftovers;
- [ ] Docker/middleware boot state converges without an unresolved `FAILED` race;
- [ ] P5 cleanup is complete or every deliberately deferred item is explicitly
  tracked with evidence and owner/reason.

## Safety constraints

- No `apt` or appliance package-manager changes on TrueNAS.
- No manual deletion/recreation of `cpool/ix-apps` or `/mnt/.ix-apps`.
- No blanket Docker network prune.
- No blind disconnect/removal of a network with live endpoints.
- No forced Talos shutdown or VM poweroff in the normal reboot procedure.
- No renumbering of protected shared networks without dependency/allowlist
  migration and rollback proof.
- Do not encode application identity against an observed dynamic
  `10.200.x.0/24` bridge unless a reviewed contract deliberately makes it
  static.
- Do not delete the retained CSI smoke, its PV/VolumeAttachment evidence or its
  TrueNAS dataset/share before the publishContext/reclaim evidence has been
  captured.
- Do not use a successful post-reboot smoke to rewrite history: if CSI acceptance
  had to be deferred before reboot, keep that pre-reboot gap explicitly recorded.
