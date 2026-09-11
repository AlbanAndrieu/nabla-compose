# Homelab ordered reboot runbook

Last updated: 2026-09-11.

This runbook defines the controlled TrueNAS reboot lifecycle for the homelab.
The transaction is deliberately fail-closed and preserves one immutable
pre-reboot state snapshot from prepare through resume.

```text
reviewed Git commit
  -> immutable/checksummed reboot bundle
  -> read-only preflight
  -> persistent PREPARING manifest
  -> TrueNAS Apps stop
  -> Docker zero-running gate
  -> Talos workers .51 / .52
  -> Talos control plane .50
  -> all Talos VMs STOPPED
  -> PREPARED
  -> retry proven CSI orphans after full quiesce
  -> supported TrueNAS reboot
  -> Docker IPAM persistence
  -> Talos VM autostart
  -> Kubernetes Ready
  -> fresh CSI RWX/reclaim regression
  -> TrueNAS Apps resume from original manifest
  -> final verification
  -> bounded cleanup
```

Related evidence and design documents:

- `truenas-reboot-incident-20260911.md`;
- `truenas-csi-orphan-datasets.md`;
- `truenas-docker-ipam-roadmap.md`;
- `homelab-network-topology.md`.

## Safety rules

- `catalog/service-topology.json` and `catalog/services.json` provide the
  repository-owned dependency evidence used by the lifecycle planner.
- Stop order is the reverse of topology-derived start order.
- Required dependency cycles fail closed rather than guessing.
- TrueNAS `app.start` / `app.stop` own normal App lifecycle.
- Do not use `app.redeploy` as a generic reboot primitive.
- Do not use `docker network prune`, bulk `docker kill`, global
  Docker/containerd restart, direct VM poweroff, `talosctl shutdown --force` or
  `zfs destroy -f` in the normal procedure.
- Cleanup is not part of the reboot transaction.
- Once `--prepare` creates its persistent manifest, that manifest is the source
  of truth until the transaction completes.
- Never create a second same-boot `apps-before.json` snapshot to recover from a
  partial prepare.

## CSI baseline and historical orphan result

PR #187 restored the TrueNAS CSI controller publish path and the fresh RWX smoke
is green:

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

The historical dataset:

```text
cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530
```

had no Kubernetes PV, no VolumeAttachment, no TrueNAS NFS reference, no child
dataset and no snapshot. Before full quiesce, supported deletion returned
`EBUSY`. After every TrueNAS App, Docker container and Talos VM was stopped,
this call succeeded:

```bash
sudo midclt call zfs.resource.destroy \
  '{"path":"cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530","recursive":true}'
```

The required postcondition was then:

```text
cannot open 'cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530': dataset does not exist
```

This establishes the operational sequence for a **proven orphan**:

```text
correlate PV / VolumeAttachment / NFS / snapshots
  -> stop workloads and Apps
  -> require docker ps empty
  -> stop Talos
  -> retry supported zfs.resource.destroy
  -> verify ZFS absence
```

Do not infer success from the API return alone. TrueNAS 26 has the separately
tracked NAS-143316 false-success behavior for a higher-level dataset delete
path.

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

The orchestrator requires at least 120 seconds of VM shutdown budget. Talos is
still responsible for the graceful Kubernetes-aware shutdown. The validated
shutdown order is:

```text
172.17.0.51 worker
172.17.0.52 worker
172.17.0.50 control plane
```

All three VMs must end as `STOPPED` while retaining `autostart=true`.

## TrueNAS readiness contract

TrueNAS 26 on this host rendered a healthy readiness value as `True`, not
lowercase `true`. CLI rendering is therefore normalized for both case and
whitespace before any lifecycle decision.

Observed healthy evidence:

```text
system.ready = True
system.state = READY
/run/middleware/.bootready exists
/run/middleware/middlewared-started exists
middlewared.service = active
```

Never create `/run/middleware/.bootready` manually.

## Build an immutable reboot bundle

Do not assemble a reboot bundle manually and do not infer its identity from its
directory name. The 2026-09-11 rehearsal exposed exactly that failure mode: the
`current` pointer still referenced an older `readyfix1` bundle while a proposed
newer bundle directory had never actually been created.

Use:

```bash
cd /mnt/cpool/compose/nabla-compose

git fetch origin

sudo bash scripts/truenas/materialize-reboot-bundle.sh \
  --ref <reviewed-commit-or-branch> \
  --activate
```

The materializer:

1. resolves one exact Git commit;
2. creates a staging directory under `/mnt/cpool/tools/nabla-reboot`;
3. exports only the required catalog/operator files from that commit;
4. validates shell and Python syntax;
5. requires the reboot script to contain `--continue-prepare`;
6. writes `SOURCE_COMMIT` and `SHA256SUMS`;
7. verifies every checksum;
8. refuses silent reuse when an existing bundle bearing the same commit has
   different contents;
9. renames the staged directory atomically;
10. updates `current` atomically only after validation succeeds.

Validate the active bundle before maintenance:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

cat "${BUNDLE}/SOURCE_COMMIT"
(
  cd "${BUNDLE}"
  sha256sum -c SHA256SUMS
)

grep -n -- '--continue-prepare' \
  "${BUNDLE}/scripts/truenas/reboot-homelab.sh"
```

`reboot-homelab.sh` also verifies `SHA256SUMS` automatically when the file is
present.

## Persistent reboot state

State lives below:

```text
/mnt/cpool/var/nabla/reboot/<timestamp>-<boot-id>/
```

The transaction contains at least:

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
- `orchestrator-identity.txt` for newly created transactions;
- `prepare-history.log` for newly created/continued transactions;
- `phase`.

Prepare phases are:

```text
PREPARING
PREPARED
```

`PREPARING` is written before the first App mutation. A failure leaves the
manifest in place.

The reboot script scans existing transaction directories for the current boot
ID before creating a new prepare. It does not rely solely on the mutable
`STATE_ROOT/latest` pointer.

## Explicit maintenance-stopped Apps

Normal pre-existing `STOPPED` Apps remain stopped. For the 2026-09-11
maintenance, the reviewed exception set was:

```bash
export NABLA_REBOOT_RESUME_STOPPED_APPS="crowdsec sample"
```

Only known-good Apps intentionally stopped for maintenance belong in this set.
Pre-existing `CRASHED`/`ERROR` Apps must not be promoted into the healthy
resume set.

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

- bundle integrity is valid;
- Talos VMs match autostart/shutdown policy;
- Kubernetes is reachable;
- all three Talos APIs are reachable through `.50`;
- lifecycle waves are reviewed;
- explicit maintenance resume set is correct;
- no state is mutated.

## Phase 1 — prepare

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

1. verifies TrueNAS readiness and bundle integrity;
2. verifies Talos VM policy and cluster reachability;
3. refuses another same-boot reboot transaction;
4. snapshots Apps, VMs, Docker, Kubernetes and boot ID once;
5. stores orchestrator identity;
6. writes `PREPARING` and the `latest` pointer;
7. stops Apps according to the preserved shutdown plan;
8. requires `docker ps` to be empty;
9. gracefully shuts down `.51`, `.52`, then `.50`;
10. requires all three VMs `STOPPED`;
11. writes `PREPARED`.

It does not reboot TrueNAS.

## Partial prepare failure

If App stop, Docker zero-running gate or Talos shutdown fails after the manifest
exists:

**do not run a fresh `--prepare`.**

A second snapshot can lose Apps from the resume set. This happened during the
2026-09-11 rehearsal: the original snapshot saw 49 pre-existing STOPPED Apps;
a second accidental snapshot saw 57 because earlier shutdown work had already
mutated runtime state.

Repair only the exact blocker, then run:

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

Continuation:

- uses the existing manifest;
- requires the same boot ID;
- validates required state files;
- accepts `PREPARING` and reviewed legacy interrupted manifests;
- skips Apps already `STOPPED`;
- never regenerates `apps-before.json`, `resume-plan.json` or `resume-apps.txt`;
- records continuation in `prepare-history.log`;
- continues through Docker and Talos gates.

## Docker/containerd ghost state

An App stop may fail with:

```text
tried to kill container, but did not receive an exit event
```

Correlate Docker state before choosing a recovery action.

### Probable orphan shim

The Pi-hole incident showed:

```text
container=pihole-dns-sync
status=restarting
Running=true
Restarting=true
Pid=0
containerd-shim-runc-v2 still present
```

Use the read-only diagnostic first:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
```

Only after confirming the exact container and shim may the guarded recovery be
used:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh \
  --recover pihole-dns-sync
```

The helper refuses a live container PID and targets one exact shim. It does not
restart Docker/containerd globally.

After recovery, return to the supported App lifecycle:

```bash
sudo midclt call -j app.stop pihole
```

### `Pid=0` can be transient

Suricata briefly showed `restarting=true,pid=0`, but:

```bash
sudo docker stop -t 60 suricata
```

converged normally to `exited`. Therefore the escalation order is:

```text
normal owner/app stop
  -> normal docker stop for a known unmanaged container when appropriate
  -> inspect Running / Restarting / Pid
  -> inspect exact shim
  -> guarded shim recovery only if proven
```

## Docker zero-running gate

Before Talos shutdown:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
```

must contain no running container.

If containers remain, the reboot orchestrator prints status, PID, restart
policy and the `Pid=0` warning when relevant. It does not stop unmanaged
containers automatically.

## PREPARED acceptance and CSI retry

Cross into `PREPARED` only when:

```text
docker ps = empty
taloswk01 = STOPPED, autostart=true
taloswk02 = STOPPED, autostart=true
taloscp01 = STOPPED, autostart=true
phase = PREPARED
```

At this point retry any **already proven** CSI orphan with supported middleware
deletion and verify its absence. Do not discover and delete arbitrary datasets
as part of reboot preparation.

If a proven orphan still returns `EBUSY`, preserve evidence. Do not force it.

## Reboot boundary

Use the supported TrueNAS UI or supported `system.reboot` API only after the
PREPARED acceptance gate. Do not substitute a raw forced reboot.

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

Acceptance requires:

- boot ID changed;
- normalized `system.ready=true`;
- Docker middleware/systemd healthy;
- default Docker address pool still `10.200.0.0/16` with `/24` allocations;
- `br0=172.17.0.24/24`;
- protected `sample-observer=10.254.255.0/28` intact;
- all Talos VMs `autostart=true` and `RUNNING`;
- all Talos APIs reachable through `.50`;
- Kubernetes 3/3 Ready.

Do not resume Apps if this phase fails.

## Phase 2.5 — fresh CSI regression

The historical `pvc-0374...` orphan was removed before reboot, so it no longer
needs post-boot cleanup. Run a new disposable smoke instead:

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
actual TrueNAS-side NFS share plus dataset reclaim.

## Phase 3 — resume Apps

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_PLANNER="${BUNDLE}/scripts/truenas/plan-app-lifecycle-order.py" \
  NABLA_IPAM_CHECK_SCRIPT="${BUNDLE}/scripts/truenas/migrate-docker-address-pool.sh" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --resume
```

Only Apps captured by the original saved resume plan are started. Apps that
were already RUNNING may be skipped. Historically stopped or failed Apps are
not blanket-started.

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

The transaction is accepted only when lifecycle, cluster/network, fresh CSI and
Docker/runtime gates are green.

## Phase 5 — bounded cleanup

Only after final acceptance:

- archive the reboot manifest, boot IDs, source commit and prepare history;
- retain current and previous known-good reboot bundles;
- confirm disposable CSI smoke resources are gone;
- classify legacy Docker networks owner-by-owner;
- never use `docker network prune`;
- protect `intranet`, `traefik_network`, `sample-observer`, `nabla-security` and
  `secrets-backend`;
- keep pre-existing failed Apps as separately tracked debt.

## Emergency fallback

The normal path has no automatic forced host or VM shutdown. Do not use these
as first response:

```text
talosctl shutdown --force
vm.poweroff
bulk docker kill
docker network prune
zfs destroy -f
manual ix-apps manipulation
global Docker/containerd restart for a single ghost container
```

Prefer bounded diagnosis, exact-owner recovery, the immutable transaction
manifest and `--continue-prepare`.
