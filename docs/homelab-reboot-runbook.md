# Homelab ordered reboot runbook

Last updated: 2026-10-03.

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

- `incidents/2026-09-11-truenas-reboot.md`;
- `truenas-csi-orphan-datasets.md`;
- `truenas-docker-ipam-roadmap.md`;
- `homelab-network-topology.md`.

## TrueNAS BIA / PRA objectives

The canonical continuity targets for `resource:default/truenas` are declared in
`catalog/catalog-info.yaml`:

| Objective | Target | 2026-10-03 evidence |
| --- | --- | --- |
| Business criticality | critical | TrueNAS hosts persistent storage, Docker Apps and Talos VMs |
| MTPD / DMTP | 4 hours | unchanged; business-impact ceiling, not a measured restore duration |
| RTO | 1 hour | **target breached** during this exercise because the software reboot hung and recovery required a manual power-cycle plus an orchestrator hotfix |
| RPO | 1 hour | **not exercised** by this reboot test; no backup/restore recovery point was selected |
| MBCO | storage and priority always-on services | recovered: FOUNDATION Apps, Talos/Kubernetes and CSI NFS |

The requested DTO is represented as the existing Nabla **RTO** field; no separate
DTO annotation is introduced because the catalog already uses RTO/RPO as the
canonical BIA recovery objectives.

The 2026-10-03 exercise proves the recovery path after a manual power-cycle:

```text
PREPARED
  -> software reboot reaches reboot.target/systemd-shutdown
  -> host fails to restart automatically
  -> manual power-cycle
  -> Docker/IPAM persistence PASS
  -> Talos/Kubernetes 3/3 Ready
  -> CSI cross-node RWX + reclaim PASS
  -> explicit audited prepare->resume bundle hotfix
  -> 5/5 App resume waves PASS
  -> final --verify PASS
```

This is therefore recorded as `pra-status=tested-with-deviation` and
`pra-recovery-result=passed-after-manual-power-cycle`. It is **not** evidence
that the software reboot mechanism itself is accepted. A subsequent controlled
software reboot must complete without physical intervention before that
deviation can be closed.

RPO acceptance is also separate from reboot acceptance. A healthy ZFS pool and
zero observed data loss after reboot do not prove a one-hour RPO. That objective
requires backup/snapshot recovery evidence with a selected recovery point no
older than one hour.

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

## Docker post-boot convergence

`system.ready=True` does not imply that Apps/Docker initialization is complete.
The 2026-09-26 recovery reboot observed `docker.service=activating` while
`docker.status=INITIALIZING`.

The Docker/IPAM post-reboot gate therefore waits, with a bounded timeout, for
both `docker.service=active` and `docker.status=RUNNING` before running Docker
network or inventory commands. Docker CLI calls are also individually bounded
so initialization cannot make the operator workflow appear frozen. Terminal
middleware states `FAILED`, `MIGRATION_FAILED` and `UNCONFIGURED` still
fail immediately.

A STOPPED App set does **not** make Docker startup cheap. Before the TrueNAS
middleware can expose the App inventory, `dockerd` still has to reopen
`overlay2`, reload image/layer metadata, reconcile stopped-container metadata,
restore network/IPAM state and make its API ready. The 2026-10-03 controlled
reboot measured a notably large local state: 764 images, 7,408 top-level
`overlay2` directories and about 525 GiB in `cpool/ix-apps/docker`, while all
97 Apps remained STOPPED. Cold-start convergence took more than ten minutes.
The gate now reports an elapsed-time heartbeat so this long metadata phase is
visible rather than looking hung.

The reboot preflight runs this lightweight storage-debt audit while Docker and
Apps are still operational. `--prepare` repeats it immediately before the first
App shutdown and stores the output as
`docker-storage-debt-before.txt` in the immutable reboot transaction manifest.
Advisory debt thresholds warn but do not block the reboot.

Do not clean Docker storage during an active reboot transaction. After final
acceptance, assess the debt read-only:

```bash
sudo bash scripts/truenas/audit-docker-storage-debt.sh --check
# Optional, deliberately bounded because Docker's detailed accounting can be slow:
sudo bash scripts/truenas/audit-docker-storage-debt.sh --deep
```

Cleanup must be owner-reviewed. Do not use `docker system prune` or
`docker network prune`; prefer targeted removal of proven dangling images,
obsolete unmanaged/exited containers or build cache, understanding that image
removal can trade local metadata for later pull time.

Talos VM autostart is also treated as a convergence phase. Recovery waits
separately for all three VMs to reach `RUNNING` with `autostart=true`, then
for each Talos API endpoint, and finally for all Kubernetes Nodes to become
`Ready`. Each phase has its own bounded timeout and diagnostic output.

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

Validate the active bundle before maintenance. Reboot bundles contain only
repository-owned scripts/catalog metadata (no secret material) and are
root-owned but world-readable/traversable so the operator can inspect the exact
commit/checksums before invoking the root-only lifecycle actions:

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
- optional `operator-acceptance.json` for one reviewed accepted-with-deferred decision;
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
- if all three Talos VMs are `RUNNING`, Kubernetes and all three Talos APIs must be reachable through `.50`;
- if all three Talos VMs are already `STOPPED`, the preflight accepts that quiesced state for shutdown-only preparation, records an explicit unavailable Kubernetes snapshot marker, and does not attempt Talos API calls;
- any mixed Talos VM state fails closed;
- lifecycle waves are reviewed;
- explicit maintenance resume set is correct;
- no state is mutated.

The post-reboot gate is unchanged and strict: autostart must return all three
Talos VMs to `RUNNING`, all Talos APIs must answer, and Kubernetes must reach
3/3 Ready.

### Mixed Talos VM recovery before shutdown

Do not continue a shutdown transaction when the control-plane VM is
`STOPPED` while one or both workers are still `RUNNING`. Kubernetes cannot
coordinate a clean worker shutdown in that state.

Resolve the control-plane VM ID without guessing, start only that VM through
the supported TrueNAS API, and wait for cluster readiness:

```bash
TALOS_CP_ID="$(
  sudo midclt call vm.query '[["name","=","taloscp01"]]' |
    jq -er 'if length == 1 then .[0].id else error("taloscp01 lookup mismatch") end'
)"

sudo midclt call vm.start "${TALOS_CP_ID}" '{"overcommit":false}'

sudo midclt call vm.status "${TALOS_CP_ID}"
```

Then wait until `172.17.0.50` answers and Kubernetes returns all expected
nodes Ready before rerunning the read-only reboot preflight. Do not start or
restart the workers merely to satisfy the gate; preserve their current runtime
state.

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

## Automated recovery transaction

The 2026-09-26 incident validated a complete recovery boundary with 97 Apps
`STOPPED`, zero running Docker containers, zero `Pid=0` ghosts, then Talos
workers followed by the control-plane cleanly reaching `STOPPED` with
`autostart=true`.

For this abnormal path, use the dedicated transaction helper instead of an old
normal reboot manifest:

```bash
sudo bash scripts/truenas/recovery-reboot-homelab.sh --prepare
```

The command freezes one recovery snapshot, derives topology stop order, uses
supported `app.stop`, applies bounded App-scoped ghost repair only after a
stop failure, revisits residual ghosts belonging to Apps that were already
`STOPPED`, requires all Apps `STOPPED`, requires Docker zero-running and
zero-ghost state, then gracefully shuts down Talos `.51`, `.52`, `.50`.
It stops at `READY_TO_REBOOT`.

If interrupted before the host reboot:

```bash
sudo bash scripts/truenas/recovery-reboot-homelab.sh --continue
```

Inspect at any time:

```bash
sudo bash scripts/truenas/recovery-reboot-homelab.sh --status
```

Only after `READY_TO_REBOOT`:

```bash
sudo bash scripts/truenas/recovery-reboot-homelab.sh --reboot
```

After TrueNAS returns, do not start Apps manually:

```bash
sudo bash scripts/truenas/recovery-reboot-homelab.sh --post-reboot-check
```

This requires a changed boot ID, TrueNAS/Docker/IPAM health, no App/container
auto-resurrection, Talos autostart, Talos API reachability and Kubernetes Ready.

Recovery restore is deliberately split:

```bash
# Only Apps observed RUNNING/DEPLOYING in the frozen snapshot.
sudo bash scripts/truenas/recovery-reboot-homelab.sh --resume-safe

# Optional second pass for explicitly reviewed candidates, including prior
# CRASHED/ERROR Apps.
STATE_DIR="$(sudo cat /mnt/cpool/var/nabla/recovery/latest)"
sudo cp "${STATE_DIR}/resume-review.txt" "${STATE_DIR}/resume-approved.txt"
sudoedit "${STATE_DIR}/resume-approved.txt"
sudo bash scripts/truenas/recovery-reboot-homelab.sh --resume-reviewed
```

Never copy the whole review list blindly: historical App debt remains debt until
explicitly accepted for restart.

For normal planned maintenance, `reboot-homelab.sh --prepare` now invokes the
same bounded App-scoped ghost recovery automatically after a supported
`app.stop` failure. Set `NABLA_REBOOT_AUTO_RECOVER_GHOSTS=false` to disable
that repair path for diagnostic-only maintenance.

## Fast post-reboot ghost recovery procedure

When a reboot returns with widespread App `CRASHED`/`STOPPED` states and
Docker reports `Running/Restarting=true` with `Pid=0`, preserve recovery
intent before cleanup:

```bash
RECOVERY_DIR="/mnt/cpool/var/nabla/recovery-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 700 "${RECOVERY_DIR}"
sudo midclt call app.query |
  sudo tee "${RECOVERY_DIR}/apps-before-cleanup.json" >/dev/null
sudo jq -r '
  .[] |
  select(.state=="RUNNING" or .state=="DEPLOYING" or .state=="CRASHED") |
  .id
' "${RECOVERY_DIR}/apps-before-cleanup.json" |
  sudo tee "${RECOVERY_DIR}/resume-candidates.txt"
sudo midclt call system.boot_id |
  sudo tee "${RECOVERY_DIR}/boot-id.txt"
```

Get the read-only ghost matrix:

```bash
sudo bash scripts/truenas/recover-app-after-docker-ghost.sh --check
```

For a `STOPPED`, `CRASHED` or `ERROR` App:

```bash
sudo bash scripts/truenas/recover-app-after-docker-ghost.sh   --recover-app <app-id>
```

The helper tries supported `app.stop` first. If it fails, only containers from
that App's `ix-<app>` Compose project are considered. Automatic shim recovery
requires all of: Running or Restarting, init PID zero, and exactly one
`containerd-shim-runc-v2` matching the full container ID. Zero or multiple
matching shims fail closed.

`RUNNING` and `DEPLOYING` Apps require explicit quiesce intent:

```bash
sudo env NABLA_GHOST_RECOVERY_ALLOW_ACTIVE=true   bash scripts/truenas/recover-app-after-docker-ghost.sh   --recover-app <app-id>
```

For a reviewed full recovery reboot, generate a shutdown plan from the preserved
snapshot and process `stop_order`. Stop on the first helper failure:

```bash
sudo python3 scripts/truenas/plan-app-lifecycle-order.py   --apps "${RECOVERY_DIR}/apps-before-cleanup.json"   --states RUNNING,DEPLOYING,CRASHED,ERROR,STOPPING   --services catalog/services.json   --topology catalog/service-topology.json   --pretty |
  sudo tee "${RECOVERY_DIR}/shutdown-plan.json" >/dev/null

while IFS= read -r app; do
  state="$(sudo midclt call app.query "[[\"id\",\"=\",\"${app}\"]]" |
    jq -r 'if length==1 then .[0].state else "MISSING" end')"
  case "${state}" in
    RUNNING|DEPLOYING)
      sudo env NABLA_GHOST_RECOVERY_ALLOW_ACTIVE=true         bash scripts/truenas/recover-app-after-docker-ghost.sh --recover-app "${app}"
      ;;
    *)
      sudo bash scripts/truenas/recover-app-after-docker-ghost.sh --recover-app "${app}"
      ;;
  esac || break
done < <(sudo jq -r '.stop_order[]' "${RECOVERY_DIR}/shutdown-plan.json")
```

Before another reboot require `docker ps` empty and:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
```

to report no Running/Restarting container with `Pid=0`. Preserve the recovery
snapshot across the reboot; do not substitute an older reboot manifest.

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

TrueNAS 26 models `system.reboot` as a job with a required reason and an
optional `delay`. For an immediate reviewed reboot after `PREPARED`:

```bash
sudo midclt call -j system.reboot \
  "Nabla controlled reboot after PREPARED lifecycle gate" \
  '{"delay": null}'
```

Using `-j` is intentional because `system.reboot` is a job method. The SSH
session is expected to disconnect once the reboot begins.

## Phase 2 — post-reboot infrastructure gate

Automatic post-reboot/resume actions reject manifests older than 48 hours by
default, using the frozen `apps-before.json` timestamp. This prevents a stale
`STATE_ROOT/latest` pointer from authorizing a later unrelated reboot.
`NABLA_REBOOT_MAX_MANIFEST_AGE_SECONDS` is an explicit recovery-only override;
do not increase it unless the old frozen intent has been independently reviewed.

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

Only Apps captured by the original saved resume plan are eligible for resume.
Apps that are already `RUNNING` are **verified rather than skipped**: the
reconciler requires stable containers, waits for explicit Docker healthchecks
to become `healthy`, and accepts successful one-shot initializers as
`Exited(0)`. Failures block later waves by default.

A reviewed App may declare `x-nabla.lifecycle.blocksLaterWaves: false` when its
failure must remain visible but is not a prerequisite for unrelated services.
Vaultwarden uses this policy: it is attempted in the foundation phase, but its
failure does not stop PostgreSQL/Redis/application waves because normal boot
consumes persistent `/mnt/cpool/secrets/runtime/*` materializations. The final
resume result and strict `--verify` remain red until Vaultwarden itself is
healthy. Required topology dependencies are never bypassed by this policy.
Historically stopped or failed Apps are not blanket-started.

The immutable reboot bundle includes
`verify-app-runtime-health.sh`; therefore post-reboot acceptance does not
depend on the mutable repository checkout. Application-specific HTTP/TCP
functional probes remain an explicit post-resume validation step because the
generic lifecycle reconciler cannot safely infer every protocol contract.

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

## Reviewed operator acceptance with deferred debt

Strict `--verify` remains the technical acceptance gate. If a reboot transaction
has reviewed, non-blocking service debt that must be recorded separately from
the strict verifier, write one immutable operator annotation:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env \
  NABLA_REPO_ROOT="${BUNDLE}" \
  NABLA_REBOOT_ACCEPTANCE_NOTE="Reviewed non-blocking service debt; tracked separately" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" \
    --accept-deferred nginx-proxy-manager,openarchiver,paperless-ngx
```

The command is intentionally narrow:

- the reboot must already have happened (`boot-id-before` must differ from the
  current boot ID);
- every deferred App must already belong to the frozen `resume-apps.txt`
  membership captured before shutdown;
- the script refuses to overwrite an existing `operator-acceptance.json`;
- the annotation records the current App states plus SHA-256 fingerprints of
  `apps-before.json`, `resume-plan.json` and `resume-apps.txt`;
- the annotation does not change lifecycle ordering, membership or any saved
  manifest file;
- it does not make `--verify` pass. A later strict verification still checks
  every saved App and reports unresolved runtime debt.

Use this only to preserve the operator decision and incident context. Fix the
deferred services independently, then rerun strict `--verify` when they are
expected to satisfy the original lifecycle contract.

## Phase 5 — bounded cleanup

Strict `--verify` now persists `phase=VERIFIED`, the post-reboot boot ID and
the verification event in `prepare-history.log`. Only that state is eligible
for evidence archival.

From the activated immutable bundle:

```bash
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo bash "${BUNDLE}/scripts/truenas/archive-reboot-evidence.sh" --check
sudo bash "${BUNDLE}/scripts/truenas/archive-reboot-evidence.sh" --apply
```

The archive helper is evidence-only. It copies a reviewed allowlist from the
normal reboot manifest into
`/mnt/cpool/var/nabla/reboot-archive/<transaction>/`, creates
`ARCHIVE-MANIFEST.json` and `SHA256SUMS`, verifies an existing archive
idempotently and refuses a non-`VERIFIED` transaction. It never changes
Docker, Apps, Kubernetes or ZFS and never deletes an older archive.

After archival:

- retain the current and previous known-good reboot bundles;
- keep any `operator-acceptance.json` or resume-hotfix sidecar with the
  transaction evidence;
- confirm disposable CSI smoke resources are gone;
- classify legacy Docker networks owner-by-owner;
- never use `docker network prune`;
- protect `intranet`, `traefik_network`, `sample-observer`,
  `nabla-security` and `secrets-backend`;
- keep pre-existing failed Apps as separately tracked debt.

## Post-PRA staged restoration

After the immutable reboot transaction has reached a green `--verify`, restore
additional services with `config/truenas/restore-post-pra-core-apps.txt`.
The file is membership-only; ordering stays catalog-driven.

The lifecycle planner orders ready Apps by declared/fallback lifecycle priority,
while required topology relations override simple priority when they introduce a
dependency edge. For the current set, the expected waves are:

```text
wave 1  foundation / priority 10
        vaultwarden
```

Importance is not guessed as a synthetic score. Use the catalog fields directly:
`criticality` when declared, lifecycle `phase`/`priority`, required topology
relations, and `blocksLaterWaves`. Runtime ownership is an additional admission
gate: post-PRA staged restore sets prefer repository-owned Compose/TrueNAS Custom
Apps and deliberately exclude native Apps that are migration targets.

Vaultwarden is catalogued as `criticality=high`, `foundation/10`, with
`blocksLaterWaves=false`.

Prometheus is repository-owned Compose but is deliberately deferred: the
catalog declares the required relation `prometheus storesIn mimir`. Mimir is
part of the pending Grafana Compose stack, so staged recovery must not bypass
that required dependency merely because Prometheus can technically start and
buffer/retry remote-write failures.

AdGuard Home is excluded because it remains a native TrueNAS App pending a
reviewed Compose migration. Grafana is also excluded until its documented
native-to-Compose migration preserves/snapshots `/mnt/cpool/grafana/data` and
passes functional acceptance.

The former native Uptime Kuma App is gone. The target is **not** AutoKuma alone:
Uptime Kuma must first become a repository-owned Compose workload on `:31050`;
AutoKuma remains the repository-owned declarative reconciler that consumes the
Uptime Kuma API. Keep AutoKuma stopped until that Compose endpoint is healthy.

Validate before applying:

```bash
sudo bash scripts/truenas/restore-app-set.sh \
  --check \
  --apps-file config/truenas/restore-post-pra-core-apps.txt \
  --name post-pra-core
```

Only if that plan matches the live runtime, apply the same set with `--apply`.

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

## Foundation-specific reboot acceptance

The generic App state/health gate is necessary but not sufficient for the
foundation wave. The reboot resume reconciler also enforces the runtime
contracts that were proven during the 2026-10-03 recovery:

- `opensearch`: repair/check the `opensearch-security` datastore ownership
  before a stopped App is started;
- `docker-socket-proxy`: attach the active TrueNAS workload to the shared
  `intranet` network with the `docker-socket-proxy` alias after it reaches
  `RUNNING`;
- `pihole`: require the DNS synchronizer to resolve the proxy, avoid a restart
  loop/API-seat failure, and complete its initial sync.

These helpers are part of the immutable reboot bundle. Consequently
`reboot-homelab.sh --verify` fails closed when the frozen resume membership is
middleware-`RUNNING` but one of these foundation contracts is not satisfied.

For the controlled acceptance reboot, materialize from the reviewed checkout
and execute lifecycle operations from the activated immutable bundle:

```bash
sudo bash scripts/truenas/materialize-reboot-bundle.sh --ref HEAD --activate
BUNDLE="$(cat /mnt/cpool/tools/nabla-reboot/current)"

sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --check

sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --prepare
# perform the supported TrueNAS reboot

sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --post-reboot-check
sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --resume
sudo env NABLA_REPO_ROOT="${BUNDLE}" \
  bash "${BUNDLE}/scripts/truenas/reboot-homelab.sh" --verify
```

Do not mark the PRA acceptance complete from `app.query state=RUNNING` alone.
