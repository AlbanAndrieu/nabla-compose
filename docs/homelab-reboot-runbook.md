# Homelab ordered reboot runbook

Last updated: 2026-09-11.

This runbook defines the controlled TrueNAS reboot lifecycle for the homelab:

```text
CSI pre-reboot acceptance
  -> reboot preflight
  -> persistent PREPARING manifest
  -> TrueNAS Apps stop
  -> Docker/containerd zero-running gate
  -> Kubernetes workload drain through Talos
  -> Talos workers
  -> Talos control plane
  -> PREPARED
  -> TrueNAS reboot
  -> Docker IPAM persistence
  -> Talos VM autostart
  -> Kubernetes Ready
  -> CSI post-reboot regression
  -> TrueNAS Apps resume from saved manifest
  -> final verification
  -> bounded cleanup
```

It complements:

- `truenas-docker-ipam-roadmap.md`;
- `truenas-csi-orphan-datasets.md`;
- `homelab-network-topology.md`.

## Design rules

- `catalog/service-topology.json` plus `catalog/services.json` are the
  repository-owned dependency evidence.
- Stop order is the reverse of topology-derived start order.
- Required dependency cycles fail closed rather than guessing.
- TrueNAS `app.start` / `app.stop` own normal App lifecycle. The reboot path
  does not use `app.redeploy`.
- No `docker network prune`, bulk `docker kill`, direct VM poweroff or
  `talosctl shutdown --force` belongs in the normal procedure.
- A Kubernetes `Ready` cluster is not sufficient for stateful acceptance:
  TrueNAS CSI provisioning, publishContext, RWX and reclaim must also be green.
- Cleanup is never folded into the reboot transaction.
- Once `--prepare` has created its persistent manifest, that manifest is the
  source of truth for the transaction. Never create a second `apps-before`
  snapshot to recover from a partial prepare.

## Current CSI status

PR #187 is merged and the fresh CSI path is accepted:

```text
PVC Bound
  -> VolumeAttachment attached=true
  -> publishContext protocol=nfs
  -> nfsServer=172.17.0.24
  -> nfsPath=/mnt/cpool/k8s/csi/pvc-...
  -> writer on worker A
  -> reader on worker B
  -> marker preserved
  -> namespace/PV reclaimed
  -> TrueNAS NFS share removed
  -> fresh CSI dataset removed
```

The historical dataset
`cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530` remains a separately
tracked orphan candidate:

- Kubernetes PV absent;
- VolumeAttachment absent;
- TrueNAS NFS reference absent;
- no snapshots or child datasets;
- dataset is a real ZFS filesystem even when it is absent from the TrueNAS
  Storage UI;
- `zfs.resource.destroy` has returned `EBUSY`.

See `truenas-csi-orphan-datasets.md`. Do not use `zfs destroy -f`. Retry the
supported destroy only after quiescing and, if still necessary, after the
planned reboot.

## Talos VM steady-state policy

| VM | Role | Address |
| --- | --- | --- |
| `taloscp01` | control plane / etcd | `172.17.0.50` |
| `taloswk01` | worker | `172.17.0.51` |
| `taloswk02` | worker | `172.17.0.52` |

OpenTofu owns:

```hcl
talos_vm_autostart        = true
talos_vm_shutdown_timeout = 180
```

The reboot orchestrator requires at least 120 seconds of graceful VM shutdown
budget. Planned shutdown still uses Talos-aware cordon/drain/shutdown; the
hypervisor timeout is a safety boundary, not the primary shutdown mechanism.

The Talos endpoint is explicit:

```text
NABLA_TALOS_ENDPOINT=172.17.0.50
```

`.50` is the API endpoint; `--nodes` selects `.51`, `.52`, then `.50` as
shutdown targets.

## TrueNAS `system.ready` contract

TrueNAS 26 on this host prints the boolean through `midclt` as `True`, not the
lowercase JSON spelling `true`.

Do not compare the CLI output case-sensitively. `reboot-homelab.sh` normalizes
the value before all `--prepare`, `--continue-prepare`, `--post-reboot-check`,
`--resume` and `--verify` readiness gates.

Observed healthy evidence on 2026-09-11:

```text
system.ready = True
system.state = READY
/run/middleware/.bootready exists
/run/middleware/middlewared-started exists
middlewared.service = active
core.get_jobs RUNNING/WAITING = []
```

Never create `/run/middleware/.bootready` manually. It is evidence that
middleware boot progressed, not a recovery switch.

## Persistent operator bundle

Do not run the lifecycle from `/tmp`. Materialize a reviewed commit to
`/mnt/cpool/tools/nabla-reboot/<sha>` and keep
`/mnt/cpool/tools/nabla-reboot/current` as the pointer.

For a temporary reviewed hotfix, use a distinct bundle suffix and store both the
source commit and patch checksum. Do not silently overwrite a directory named
after a Git commit with content that no longer matches that commit.

The 2026-09-11 maintenance used:

```text
source commit:
540ffa65df7a59259c1a7402d71f1f2dcea5d0ce

temporary bundle suffix:
-readyfix1

temporary delta:
normalize midclt system.ready True/true
```

The repository implementation now contains the permanent readiness
normalization, so future bundles should be built directly from the merged
revision instead of carrying `readyfix1`.

## Persistent reboot state

State lives under:

```text
/mnt/cpool/var/nabla/reboot/<timestamp>-<boot-id>/
```

The manifest contains:

- `apps-before.json`;
- `vms-before.json`;
- `docker-config-before.json`;
- `docker-networks-before.txt`;
- `kubernetes-nodes-before.json`;
- `boot-id-before`;
- `shutdown-plan.json`;
- `resume-plan.json`;
- `explicit-resume.txt`;
- `intentional-stopped.txt`;
- `preexisting-failed.txt`;
- `resume-apps.txt`;
- `phase`.

Phases relevant to prepare are:

```text
PREPARING
PREPARED
```

`PREPARING` is written **before the first App mutation**. If the operation
fails, leave that manifest in place.

## Apps manually stopped for maintenance

Safe default behavior preserves Apps that were already `STOPPED`.

For this maintenance the reviewed explicit set is:

```bash
export NABLA_REBOOT_RESUME_STOPPED_APPS="crowdsec sample"
```

Only Apps known to have been healthy/active before maintenance should be added
to this list. A `CRASHED -> STOPPED` transition remains pre-existing failure
debt and must not be promoted into the healthy resume set.

There is intentionally no “resume every stopped App” mode.

## Phase 0 — read-only preflight

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

Acceptance:

- Talos VMs match autostart/shutdown policy;
- Kubernetes is reachable;
- all three Talos APIs are reachable through `.50`;
- start/stop waves are reviewed;
- explicit maintenance resume set is correct;
- preflight is read-only.

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

The script:

1. verifies TrueNAS readiness;
2. refuses to start a new transaction when an incomplete prepare already exists
   on the current boot;
3. snapshots Apps, VMs, Docker, Kubernetes and boot ID;
4. writes `phase=PREPARING`;
5. writes the `latest` pointer;
6. stops Apps according to the preserved shutdown plan;
7. requires no running Docker container;
8. gracefully shuts down Talos `.51`, `.52`, `.50`;
9. requires all three VMs `STOPPED`;
10. writes `phase=PREPARED`.

The script does **not** reboot the host.

## Partial `--prepare` failure: preserve and continue

A partial prepare is expected to be recoverable. If any App stop, Docker gate
or Talos shutdown fails after the manifest has been created:

**do not rerun `--prepare`.**

Why: a second fresh prepare would snapshot Apps already stopped by the first
attempt and could incorrectly classify them as intentionally stopped. That
would corrupt the post-reboot resume intent.

After diagnosing and repairing the exact blocker, continue with:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  NABLA_TALOS_ENDPOINT="172.17.0.50" \
  NABLA_REBOOT_RESUME_STOPPED_APPS="${NABLA_REBOOT_RESUME_STOPPED_APPS:-}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --continue-prepare
```

`--continue-prepare`:

- reuses `STATE_ROOT/latest`;
- validates required manifest files;
- requires the same TrueNAS boot ID;
- accepts `PREPARING`;
- also adopts a legacy interrupted manifest with no `phase` marker when the
  original plan files and boot ID are intact;
- skips Apps that already reached `STOPPED`;
- never regenerates `apps-before.json`, `resume-plan.json` or `resume-apps.txt`;
- continues to the Docker zero-running gate and Talos shutdown.

A fresh `--prepare` explicitly refuses to overwrite an incomplete same-boot
transaction.

## Docker/containerd ghost-state diagnostic

An App stop can fail with:

```text
tried to kill container, but did not receive an exit event
```

Do not assume that means a live container process is unkillable.

The 2026-09-11 Pi-hole incident demonstrated this state:

```text
container = pihole-dns-sync
Docker Status = restarting
Running=true
Restarting=true
Pid=0
containerd-shim-runc-v2 still present
```

That means there is no live container init PID, while a per-container shim and
Docker bookkeeping remain.

The reboot orchestrator prints container state automatically after a failed
`app.stop`. The standard platform diagnostic also includes:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
```

This read-only command reports candidates where Docker says
`Running=true` or `Restarting=true` while `Pid=0`.

### Guarded orphan-shim recovery

Recovery is deliberately explicit and single-container:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh \
  --recover pihole-dns-sync
```

The helper refuses recovery unless all of the following hold:

1. Docker still resolves the exact container;
2. `.State.Pid == 0`;
3. Docker still reports Running or Restarting;
4. exactly one `containerd-shim-runc-v2` process contains the exact full
   container ID;
5. the shim command line is revalidated immediately before signaling.

Then it:

1. sets the exact container restart policy to `no`;
2. sends SIGTERM to that exact shim PID;
3. uses SIGKILL only if that same shim ignores SIGTERM;
4. waits for Docker state to converge;
5. never calls `docker kill`;
6. never uses `pkill`/`killall`;
7. never restarts Docker/containerd globally.

After recovery, retry the supported App lifecycle call:

```bash
sudo midclt call -j app.stop pihole
```

Observed successful postcondition on 2026-09-11:

```text
pihole app = STOPPED
pihole-dns-sync = absent
pihole = absent
```

The runtime log also showed the exact orphan shim disconnect and containerd
cleanup. This was pre-existing runtime debt, not a defect created by the reboot
orchestrator.

## Why Pi-hole is a useful special case

`pihole-dns-sync` is a configuration reconciler, not the authoritative DNS data
store. It binds `/mnt/cpool/traefik` and consumes Pi-hole plus the restricted
Docker socket proxy.

Its restart loop had already been separately tracked. During a planned reboot,
a failed Pi-hole App stop must still fail closed, but a verified `Pid=0`
orphan-shim condition can be recovered without restarting the entire Docker
daemon.

See `apps/pihole/README.md` for Pi-hole-specific recovery details.

## Docker zero-running gate

Before Talos shutdown:

```bash
docker ps
```

must contain no running container.

The orchestrator intentionally refuses host/Talos shutdown while unmanaged or
stuck Docker workloads remain. A ghost state should be repaired first and the
same prepare transaction continued.

## CSI orphan check after real quiesce

Only after the existing transaction reaches `PREPARED` should the historical
CSI orphan be retried:

```bash
DATASET='cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530'

sudo midclt call zfs.resource.destroy \
  "{\"path\":\"${DATASET}\",\"recursive\":true}" || true

sudo zfs list "${DATASET}" 2>&1 || true
```

If it remains `EBUSY` with Apps, Docker and Talos quiesced, do not force it.
Proceed with the planned supported reboot and retry post-boot.

## Reboot boundary

Cross the reboot boundary only when:

```text
phase = PREPARED
docker ps = empty
Talos VMs = STOPPED
```

Use the TrueNAS UI or supported `system.reboot` API. Do not use a raw host
`reboot` command as a substitute for the appliance lifecycle.

## Phase 2 — post-reboot infrastructure gate

After TrueNAS returns:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  NABLA_TALOS_ENDPOINT="172.17.0.50" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --post-reboot-check
```

Acceptance:

- TrueNAS boot ID changed;
- normalized `system.ready` is true;
- Docker middleware and systemd runtime are healthy;
- Docker default address pool remains `10.200.0.0/16` with `/24` allocations;
- `br0=172.17.0.24/24`;
- protected `sample-observer=10.254.255.0/28` remains intact;
- all three Talos VMs are `autostart=true` and `RUNNING`;
- all three Talos APIs respond via `.50`;
- Kubernetes reaches 3/3 Ready.

Do not resume Apps if this phase fails.

## Phase 2.5 — CSI regression before App resume

Retry the historical orphan first if it survived the reboot, then run a fresh
CSI smoke:

```bash
mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --check
mise exec -- bash scripts/talos/validate-csi-prereqs.sh

CSI_SMOKE_KEEP_ON_FAILURE=true \
CSI_PVC_TIMEOUT_SECONDS=180 \
CSI_ATTACHMENT_TIMEOUT_SECONDS=60 \
CSI_POD_READY_TIMEOUT_SECONDS=300 \
  mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

Acceptance requires fresh provisioning, publishContext, cross-worker RWX and
actual TrueNAS-side share/dataset reclaim.

Do not infer reclaim merely from a successful middleware return; verify the
postcondition. TrueNAS 26 has an upstream dataset-delete false-success defect
documented in `truenas-csi-orphan-datasets.md`.

## Phase 3 — resume Apps

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --resume
```

Only Apps in the saved `resume-plan.json` are started.

Pre-existing `CRASHED`/`ERROR` Apps are not promoted into the healthy resume
set. Apps that were intentionally stopped remain stopped unless they were
explicitly included before the original `--prepare`.

## Phase 4 — final acceptance

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --verify

bash scripts/talos/validate-cluster.sh
bash scripts/talos/smoke-kubernetes-network.sh
bash scripts/talos/install-truenas-csi-nfs.sh --check

sudo bash scripts/truenas/audit-docker-network-migration.sh --check
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
```

The transaction is accepted only when the reboot lifecycle, cluster/network
checks, CSI smoke and Docker/runtime diagnostics are green.

## Phase 5 — bounded cleanup

Only after Phase 4 is green:

- archive reboot manifest, boot IDs and exact source SHA;
- retain the current bundle plus rollback evidence;
- remove disposable CSI smoke resources only after reclaim proof;
- classify any surviving CSI dataset before deletion;
- review remaining `172.16.x.0/24` Docker networks owner-by-owner;
- never use `docker network prune`;
- keep protected networks including `intranet`, `traefik_network`,
  `sample-observer`, `nabla-security` and `secrets-backend`;
- keep pre-existing failed Apps as separately tracked debt;
- remove superseded ownership only after persistent data, networks and secrets
  are proven.

## Emergency fallback

The normal path has no automatic forced host or VM shutdown.

Do not use these as first response:

```text
talosctl shutdown --force
vm.poweroff
bulk docker kill
docker network prune
zfs destroy -f
manual ix-apps manipulation
global Docker/containerd restart for a single ghost container
```

Prefer bounded diagnosis, exact-owner recovery, the persistent transaction
manifest and `--continue-prepare`.
