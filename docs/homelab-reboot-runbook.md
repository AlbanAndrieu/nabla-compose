# Homelab ordered reboot runbook

Last updated: 2026-09-11.

This runbook defines the controlled TrueNAS reboot lifecycle for the homelab:

```text
CSI retained-evidence acceptance
  -> TrueNAS Apps stop
  -> Kubernetes workload drain through Talos
  -> Talos worker VMs
  -> Talos control-plane VM
  -> TrueNAS reboot
  -> Talos VM autostart
  -> Kubernetes Ready / uncordon
  -> CSI post-reboot storage regression
  -> TrueNAS Apps in dependency order
  -> final verification
  -> bounded post-reboot cleanup
```

It complements `homelab-network-topology.md` and
`truenas-docker-ipam-roadmap.md`.

## Design rules

- `catalog/service-topology.json` plus `catalog/services.json` are the
  repository-owned dependency evidence.
- `x-nabla` is metadata. Docker Compose ignores `x-*`; it does not itself
  enforce cross-App startup order.
- `scripts/truenas/plan-app-lifecycle-order.py` translates lifecycle-relevant
  `strength=required` relations into an App-level DAG: `dependsOn`,
  `consumesApi`, `storesIn`, `authenticatesVia` and `routesTo` make the target
  start before the source; `providesApi` makes the source start before the
  target.
- Stop order is the reverse of start order.
- Required dependency cycles fail closed rather than guessing.
- Services without a `runtime.provider=truenas-app` / `runtime.appId` mapping
  are reported as unmapped. They stop before topology-mapped Apps and start
  after them.
- TrueNAS `app.start`/`app.stop` are used for reboot lifecycle operations. The
  normal reboot workflow never uses `app.redeploy`.
- No `docker network prune`, direct bulk `docker stop`, forced VM poweroff, or
  Talos `--force` shutdown is part of the normal procedure.
- A Kubernetes `Ready` cluster is not sufficient to resume stateful workloads:
  the TrueNAS CSI storage path must also pass its explicit gate.
- Cleanup is never folded into the reboot transaction. It begins only after
  `--verify` is GREEN and the storage regression is GREEN.

## Current CSI gate — PR #187

PR #187 (`fix/truenas-csi-publish-context`) restores the TrueNAS CSI v1.0.3
controller-publish contract:

```text
CSIDriver attachRequired=true
  -> VolumeAttachment
  -> csi-attacher
  -> ControllerPublishVolume
  -> VolumeAttachment.status.attachmentMetadata
       protocol=nfs
       nfsServer=172.17.0.24
       nfsPath=/mnt/cpool/k8s/csi/pvc-...
  -> NodeStageVolume
  -> NFS mount
```

The current retained smoke is useful causal evidence and must not be discarded
just to make the reboot easier:

- PVC `nabla-csi-rwx` is `Bound`;
- PV `pvc-03741395-a00a-4eaf-a04e-da10e08ec530` exists;
- writer `csi-writer` is still `ContainerCreating` on `talos-7fc-fdt`;
- VolumeAttachment
  `csi-2db054df7894042dbfee6309d758e9540ff5b11a2191d8316c58b3cd634a8712`
  exists but is currently `attached=false`;
- the controller rollout has two generations; the old Pod does not contain
  `csi-attacher`, while the new generation is expected to contain it.

A planned reboot **must not be used as the fix for this incomplete rollout**.
Before `--prepare`, identify the new controller Pod explicitly and preserve the
actual controller-publish evidence:

```bash
mise exec -- kubectl -n truenas-csi get deployment,rs,pod \
  -l app=truenas-csi-controller -o wide

mise exec -- kubectl -n truenas-csi describe deployment truenas-csi-controller

mise exec -- kubectl -n truenas-csi get pods \
  -l app=truenas-csi-controller \
  -o custom-columns='POD:.metadata.name,CREATED:.metadata.creationTimestamp,READY:.status.containerStatuses[*].ready,CONTAINERS:.spec.containers[*].name'
```

Identify the exact **new** Pod containing `csi-attacher`, then use its Pod name
rather than `deployment/truenas-csi-controller`:

```bash
mise exec -- kubectl -n truenas-csi logs <NEW_POD> \
  -c csi-attacher --since=30m

mise exec -- kubectl -n truenas-csi logs <NEW_POD> \
  -c csi-controller --since=30m

mise exec -- kubectl get volumeattachment \
  csi-2db054df7894042dbfee6309d758e9540ff5b11a2191d8316c58b3cd634a8712 \
  -o yaml
```

Pre-reboot CSI acceptance requires all of the following:

1. the old controller generation terminates and the Deployment rollout is
   complete;
2. the retained VolumeAttachment becomes `attached=true`;
3. `attachmentMetadata.protocol=nfs`;
4. `attachmentMetadata.nfsServer=172.17.0.24`;
5. `attachmentMetadata.nfsPath` is non-empty and references the retained PVC;
6. the retained writer becomes `Running` without recreating the PVC merely to
   hide the original failure;
7. worker A writes a marker and worker B reads the same marker after writer
   removal;
8. after evidence capture, deleting the disposable smoke namespace causes the
   PV, TrueNAS share and CSI dataset to be reclaimed;
9. a fresh clean smoke passes once, proving new-object provisioning as well as
   retained-object recovery.

The namespace PodSecurity baseline warning is expected when the CSI namespace
uses `enforce=privileged` with baseline audit/warn. It is not, by itself, the
cause of the attach failure.

If an operationally mandatory reboot cannot wait for this CSI acceptance,
record it explicitly as `CSI_ACCEPTANCE_DEFERRED` and persist the Pod,
ReplicaSet, Deployment, VolumeAttachment and controller logs first. A healthy
post-reboot smoke must not be used to claim that the original pre-reboot
`attached=false` cause was proven.

When PR #187 has not yet been merged, record the exact tested PR SHA with the
reboot evidence and execute its CSI checks from that exact reviewed checkout;
do not silently test a moving branch tip.

## Talos VM steady-state policy

| VM | Role | Address |
| --- | --- | --- |
| `taloscp01` | control plane / etcd | `172.17.0.50` |
| `taloswk01` | worker | `172.17.0.51` |
| `taloswk02` | worker | `172.17.0.52` |

OpenTofu owns the steady-state VM policy:

```hcl
talos_vm_autostart        = true
talos_vm_shutdown_timeout = 180
```

`autostart=true` makes the VMs start when TrueNAS boots. TrueNAS does not need
a repository-defined VM start sequence for recovery: all three VMs may be
started by the host as its VM service converges, and the reboot orchestrator
gates the next phase on all Talos APIs plus all Kubernetes nodes becoming
Ready. The ordered lifecycle requirement is strict on shutdown: workers are
drained/shut down before the single-control-plane/etcd VM.

The 180-second hypervisor timeout is a safety window, not the primary
Kubernetes shutdown mechanism. Planned reboots use `talosctl shutdown` without
`--force`, so Talos cordons/drains Kubernetes before the guest shuts down.

Reconcile the current TrueNAS runtime before the first controlled reboot:

```bash
sudo bash scripts/truenas/reconcile-talos-vm-policy.sh --check
sudo bash scripts/truenas/reconcile-talos-vm-policy.sh --apply
sudo bash scripts/truenas/reconcile-talos-vm-policy.sh --check
```

The OpenTofu/Terragrunt plan must subsequently show only expected in-place
policy reconciliation. Never accept VM create/destroy/replace merely to enable
autostart.

### Talos endpoint contract

The reboot orchestrator deliberately separates the Talos **endpoint** from the
target node. The single control-plane VM `172.17.0.50` is the default API
endpoint and `--nodes` selects `.50`, `.51` or `.52` as the operation target:

```text
NABLA_TALOS_ENDPOINT=172.17.0.50
```

This avoids relying on whatever endpoint list happens to be stored in the
operator `talosconfig`. The preflight and post-reboot gate preserve Talos stderr
and report both `target` and `endpoint`; an mTLS, RPC or connectivity failure
must remain diagnosable instead of being hidden behind `/dev/null`.

## Persistent operator bundle

Do not run the reboot lifecycle from `/tmp`: TrueNAS clears volatile state
during reboot. Before `--prepare`, materialize the exact reviewed PR commit to a
persistent bundle on `cpool` without switching the active repository worktree:

```bash
cd /mnt/cpool/compose/nabla-compose
git fetch origin feat/k8s-platform-security-tools
PIN="$(git rev-parse origin/feat/k8s-platform-security-tools)"
BUNDLE="/mnt/cpool/tools/nabla-reboot/${PIN}"

for path in \
  catalog/services.json \
  catalog/service-topology.json \
  scripts/truenas/plan-app-lifecycle-order.py \
  scripts/truenas/reconcile-talos-vm-policy.sh \
  scripts/truenas/migrate-docker-address-pool.sh \
  scripts/truenas/audit-docker-network-migration.sh \
  scripts/truenas/reboot-homelab.sh
do
  sudo install -d -m 0755 "${BUNDLE}/$(dirname "${path}")"
  git show "${PIN}:${path}" | sudo tee "${BUNDLE}/${path}" >/dev/null
done
sudo chmod 0755 "${BUNDLE}/scripts/truenas/"*.sh
sudo chmod 0644 "${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py"
printf '%s\n' "${BUNDLE}" | \
  sudo tee /mnt/cpool/tools/nabla-reboot/current >/dev/null
```

All pre/post-reboot commands can then resolve the exact same reviewed code with:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
```

This bundle is an execution snapshot, not another source of truth. The Git
branch and normal repository checkout remain canonical.

## Persistent reboot state

The orchestrator records state under:

```text
/mnt/cpool/var/nabla/reboot/<timestamp>-<boot-id>/
```

It captures pre-reboot Apps, VMs, Docker IPAM/network state, Kubernetes nodes,
TrueNAS boot ID, topology-derived shutdown/resume plans, pre-existing
stopped/failed Apps, and the exact post-reboot resume set. The state is on
`cpool`, not `/tmp`, so it survives reboot.

Also persist the following evidence before the operator reboot boundary:

- exact reboot orchestration SHA;
- exact CSI PR #187 SHA when it is still unmerged;
- successful `--check` output;
- current `docker.config`, `docker.status` and route inventory;
- current Apps snapshot and reviewed resume set;
- CSI retained-state evidence or explicit `CSI_ACCEPTANCE_DEFERRED` marker.

## Apps manually stopped for maintenance

Safe default behavior preserves every App already `STOPPED` when `--prepare`
starts. Docker state cannot reliably distinguish a deliberately disabled App
from one stopped temporarily for maintenance.

If Apps were stopped temporarily to speed up this maintenance and must come
back after reboot, list their TrueNAS App IDs explicitly before both `--check`
and `--prepare`:

```bash
export NABLA_REBOOT_RESUME_STOPPED_APPS="crowdsec sample"
```

The explicit list is stored in the persistent reboot manifest. There is
intentionally no `resume all stopped Apps` shortcut.

The IPAM helper intentionally creates its evidence snapshots as root-only
(`umask 077`). Do not weaken those permissions merely to compare snapshots. Run
`jq` through `sudo` when the current shell is not root.

When manual stops happened during the current IPAM maintenance, compare a
pre-stop Apps snapshot with the latest one before deciding the resume set. A
service is an automatic maintenance-resume candidate only when it was `RUNNING`
or `DEPLOYING` before the manual stop and is now `STOPPED`. A
`CRASHED -> STOPPED` transition is evidence of a pre-existing failure, not
evidence that the service belonged to the healthy resume set.

```bash
sudo jq -n \
  --slurpfile before /tmp/truenas-docker-ipam-20260911-030029.apps.json \
  --slurpfile now /tmp/truenas-docker-ipam-20260911-033708.apps.json '
    ($before[0] | map({key:.id,value:.state}) | from_entries) as $old |
    $now[0][] |
    ($old[.id] // "UNKNOWN") as $before_state |
    select(
      .state == "STOPPED" and
      ($before_state == "RUNNING" or $before_state == "DEPLOYING")
    ) |
    [.id, $before_state, .state] | @tsv
  ' -r
```

For the 2026-09-11 snapshots used during this migration, that safety rule
selects `crowdsec` and `sample`. The other listed transitions were already
`CRASHED` before being manually stopped and therefore stay outside the
automatic reboot resume set.

After review, derive the space-separated resume set without changing snapshot
permissions:

```bash
NABLA_REBOOT_RESUME_STOPPED_APPS="$(
  sudo jq -n \
    --slurpfile before /tmp/truenas-docker-ipam-20260911-030029.apps.json \
    --slurpfile now /tmp/truenas-docker-ipam-20260911-033708.apps.json '
      ($before[0] | map({key:.id,value:.state}) | from_entries) as $old |
      $now[0][] |
      ($old[.id] // "UNKNOWN") as $before_state |
      select(
        .state == "STOPPED" and
        ($before_state == "RUNNING" or $before_state == "DEPLOYING")
      ) |
      .id
    ' -r | paste -sd" " -
)"
export NABLA_REBOOT_RESUME_STOPPED_APPS
printf 'Maintenance-stopped Apps selected for resume:\n%s\n' \
  "${NABLA_REBOOT_RESUME_STOPPED_APPS}"
```

Review that result before `--prepare`; do not automatically treat every current
`STOPPED` App as maintenance-stopped and do not auto-promote a previously
`CRASHED` App into the reboot resume manifest.

## Phase 0 — read-only preflight

**Entry condition:** the CSI retained-state gate above is accepted, or an
operational exception explicitly records `CSI_ACCEPTANCE_DEFERRED` with evidence.

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  NABLA_TALOS_ENDPOINT="172.17.0.50" \
  NABLA_REBOOT_RESUME_STOPPED_APPS="${NABLA_REBOOT_RESUME_STOPPED_APPS:-}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --check
```

The preflight verifies the three Talos VMs and their boot policy,
operator-private `talosctl`/`kubectl` credentials, Kubernetes reachability, and
direct Talos API access to `.50/.51/.52` through the control-plane endpoint
`.50`. It changes nothing. If a Talos call fails, the diagnostic shows both the
endpoint and the target plus the underlying client error.

Do not continue to `--prepare` until this command is clean and its generated
start/stop waves plus unmapped Apps have been reviewed.

## Phase 1 — prepare the host

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  NABLA_TALOS_ENDPOINT="172.17.0.50" \
  NABLA_REBOOT_RESUME_STOPPED_APPS="${NABLA_REBOOT_RESUME_STOPPED_APPS:-}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --prepare
```

The procedure:

1. writes the persistent reboot manifest;
2. stops all non-STOPPED TrueNAS Apps in reverse topology order;
3. requires `docker ps` to contain no running container afterwards;
4. gracefully shuts down Talos workers `.51` then `.52` through endpoint `.50`;
5. gracefully shuts down control plane/etcd `.50` last;
6. requires all three TrueNAS VMs to become `STOPPED`;
7. records `PREPARED`.

The script deliberately does not issue the host reboot. This retains a final
operator boundary after all shutdown preconditions pass. Reboot through the
TrueNAS UI or supported `system.reboot` API.

Before crossing that boundary, inspect the persistent state directory and copy
any last volatile `/tmp` evidence that must survive reboot to `cpool`.

If any App, unmanaged Docker container, Kubernetes drain or Talos shutdown
fails, do not reboot until the failure is understood.

## Phase 2 — post-reboot infrastructure gate

After TrueNAS is reachable again, use the pinned bundle, not a newly fetched
branch tip:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  NABLA_TALOS_ENDPOINT="172.17.0.50" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --post-reboot-check
```

Acceptance requires:

- `system.ready=true` and a changed TrueNAS boot ID;
- Docker IPAM still `10.200.0.0/16,size=24` without reapplication;
- Docker systemd service and TrueNAS middleware both RUNNING;
- `br0=172.17.0.24/24` and LAN default route unchanged;
- protected observer network integrity;
- all three Talos VMs `autostart=true` and `RUNNING`;
- direct Talos API access through endpoint `.50`;
- every Kubernetes node Ready.

Do not resume Apps if this gate fails. If Docker middleware is FAILED while
dockerd is active, capture middleware jobs and boot logs before repairing it.

## Phase 2.5 — post-reboot CSI/storage regression gate

Run this **before** `--resume`. Stateful Apps must not be restarted onto an
unproven storage path.

From the exact reviewed CSI code (PR #187 SHA when still unmerged, otherwise the
merged `master` revision):

```bash
mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --check
mise exec -- bash scripts/talos/validate-csi-prereqs.sh

CSI_SMOKE_KEEP_ON_FAILURE=true \
CSI_PVC_TIMEOUT_SECONDS=180 \
CSI_ATTACHMENT_TIMEOUT_SECONDS=60 \
CSI_POD_READY_TIMEOUT_SECONDS=300 \
  mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

Acceptance requires the smoke to prove:

```text
PVC Bound
  -> VolumeAttachment attached=true
  -> attachmentMetadata protocol=nfs + nfsServer + nfsPath
  -> writer Running on worker A
  -> marker persisted
  -> reader on worker B reads same marker
  -> namespace/PV reclaimed
  -> TrueNAS CSI dataset/share removed
```

If the post-reboot smoke fails, keep its resources/evidence and stop here. Do
not resume storage-dependent Apps and do not manually delete the CSI dataset or
share just to clear the failed test.

## Phase 3 — resume Kubernetes scheduling and Apps

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --resume
```

The script waits for all Kubernetes nodes to be Ready, idempotently uncordons
them, then starts only Apps in the saved resume manifest, wave-by-wave in
topology dependency order using `app.start`.

Pre-existing `CRASHED`/`ERROR` Apps are not automatically restarted. Apps that
were intentionally `STOPPED` remain stopped unless explicitly included in
`NABLA_REBOOT_RESUME_STOPPED_APPS` before `--prepare`.

For the current maintenance snapshot, the explicitly reviewed maintenance
resume set is `crowdsec sample`; do not reuse the earlier broad list that also
contained services already `CRASHED` before maintenance.

## Phase 4 — final acceptance

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"
sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --verify
```

Then run the broader cluster gates as the non-root Kubernetes operator:

```bash
bash scripts/talos/validate-cluster.sh
bash scripts/talos/smoke-kubernetes-network.sh
bash scripts/talos/install-truenas-csi-nfs.sh --check
```

And re-audit Docker network migration:

```bash
sudo bash scripts/truenas/audit-docker-network-migration.sh --check
```

Any remaining `172.16.x.0/24` network must be a documented protected/shared
contract or a tracked migration candidate.

The reboot transaction is accepted only when `--verify`, the cluster/network
gates and the post-reboot CSI smoke are GREEN. A pre-existing application
failure may remain as separately tracked debt, but it must not be silently
reclassified as a reboot regression or as a successful recovery.

## Phase 5 — bounded post-reboot cleanup

**Entry condition: Phase 4 is GREEN.** Do not run this phase to rescue or mask a
failed reboot.

### 5.1 Archive the known-good evidence

Persist outside `/tmp`:

- reboot manifest and boot IDs;
- exact orchestration and CSI SHAs;
- `app.query` before/after snapshots;
- `docker info`, `docker ps`, route table and complete Docker network inventory;
- relevant middleware/docker boot logs;
- Talos/Kubernetes node evidence;
- CSI attach/publishContext/RWX/reclaim evidence.

Retain the current known-good bundle plus at least one previous rollback bundle
until another normal reboot is accepted. Old bundles are removed only under an
explicit retention policy.

### 5.2 Clean disposable CSI state

After successful reclaim, verify there is no leftover:

- `nabla-csi-smoke` namespace;
- writer/reader Pod;
- smoke PVC/PV;
- TrueNAS CSI VolumeAttachment;
- corresponding TrueNAS share/dataset.

If Kubernetes objects are gone but the share/dataset remains, classify it as a
CSI orphan and collect reclaim/controller evidence first. Do not start with
manual share deletion or `zfs destroy`.

### 5.3 Converge legacy Docker networks

Run:

```bash
sudo bash scripts/truenas/audit-docker-network-migration.sh --check
```

For every surviving legacy `172.16.x.0/24` network record its name/subnet,
endpoint count, Compose/TrueNAS owner, external/shared semantics and relevant
sandbox/container references.

Never generically remove these protected networks:

```text
intranet
traefik_network
sample-observer
nabla-security
secrets-backend
```

A generic legacy network is removable only when all are true:

1. zero live endpoints;
2. not required external/shared infrastructure;
3. owner/reference evidence proves it stale or orphaned.

Remove only small reviewed batches, capture before/after inventories and daemon
logs, and rerun the audit after every batch. Never use `docker network prune`.

For app-owned networks, migrate through the canonical owner lifecycle so the
network is recreated under `10.200.0.0/16`. Raw `docker network rm` alone is not
owner convergence and can simply recreate the old definition.

Historical `sandbox ... not found` messages are correlation evidence, not a
deletion instruction. Do not edit containerd state directly solely to silence
those warnings.

### 5.4 Converge application ownership and failures

Compare the persistent pre-maintenance state, resume manifest and post-reboot
`app.query`.

- Explain every state difference.
- Keep Apps that were already `CRASHED` before maintenance as independent debt.
- Do not automatically start them just because the reboot succeeded.
- Find direct-Compose versus TrueNAS-managed duplicates and remove the
  superseded owner only after the canonical replacement, volumes/bind mounts,
  networks and secrets are proven.
- Preserve persistent datasets/bind mounts unless a separate data deletion is
  explicitly reviewed.

### 5.5 Cleanup acceptance

After cleanup, require:

```text
TrueNAS system ready
Docker systemd active + middleware RUNNING
Docker default IPAM = 10.200.0.0/16 /24 allocations
br0 = 172.17.0.24/24, default gateway = 172.17.0.1
Talos/Kubernetes = 3/3 Ready
CSI clean cross-worker smoke = GREEN
expected-running Apps = healthy
intentionally stopped Apps = still stopped
pre-existing failed Apps = separately tracked
remaining legacy networks = documented exception or named owner migration
```

Every deferred cleanup must remain in the roadmap with its reason/evidence. A
successful reboot is not the signal to erase diagnostic history.

## Emergency fallback

The normal path has no automatic forced shutdown. TrueNAS `vm.stop` can request
graceful guest shutdown without forcing after timeout, but it does not replace
Talos-aware Kubernetes cordon/drain. Use it only after diagnosing why the Talos
API path failed.

Never use `talosctl shutdown --force`, `vm.poweroff`, a bulk Docker kill,
`docker network prune`, manual CSI dataset destruction or ix-apps manipulation
as the first response to a planned reboot.
