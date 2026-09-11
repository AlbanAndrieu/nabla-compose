# TrueNAS CSI orphan datasets

Last updated: 2026-09-11.

This runbook documents how to identify and investigate dynamically-created
TrueNAS NFS CSI datasets that remain below `cpool/k8s/csi` after Kubernetes has
reclaimed the corresponding PersistentVolume.

The diagnostic is deliberately read-only. Do not delete a dataset merely
because it is not visible in the TrueNAS web UI or because its mountpoint looks
like an ordinary directory.

## Important TrueNAS 26 observations

On the current TrueNAS 26.0.0-BETA.3 host, dynamically-created CSI datasets
such as `cpool/k8s/csi/pvc-...` have been observed to be absent from the Storage
UI while they are still present in ZFS and returned by middleware queries.
Therefore the web UI is **not authoritative evidence of absence** for this CSI
path.

Use ZFS and middleware inventory instead:

```bash
DATASET='cpool/k8s/csi/pvc-...'

sudo zfs list -H -o name,type,mounted,mountpoint,used "$DATASET"
sudo midclt call pool.dataset.query |
  jq --arg ds "$DATASET" '[.[] | select(.id == $ds)]'
```

A dataset may report `mounted=no` while its configured mountpoint remains as a
normal directory below the mounted parent `cpool/k8s/csi`. Seeing that directory
with `ls` does not mean the ZFS dataset has disappeared.

## TrueNAS 26 false-success delete regression

TrueNAS middleware issue `NAS-143316` / upstream PR
<https://github.com/truenas/middleware/pull/19637> documents a regression in
TrueNAS 26 where `pool.dataset.delete` can return `true` even though the
underlying ZFS destroy failed.

`zfs.resource.destroy_impl` reports some failures as a `(failed, errnum)` return
value rather than raising. The affected `pool.dataset.delete` implementation
ignored that tuple and returned `True` unconditionally. A typical consequence is
an `EBUSY` destroy failure that is incorrectly reported as success while the
dataset remains.

Operational rule:

> Never treat `pool.dataset.delete -> True` as sufficient reclaim evidence on an
> affected TrueNAS 26 host. Always verify that both ZFS and middleware no longer
> expose the dataset.

For diagnosis, `zfs.resource.destroy` is useful because it checks the destroy
result and surfaces the real error instead of silently reporting success:

```bash
sudo midclt call zfs.resource.destroy \
  '{"path":"cpool/k8s/csi/pvc-...","recursive":true}'
```

Do not use that command until Kubernetes and NFS references have been proven
absent. It is a destructive operation.

## Orphan definition

A CSI dataset is a **definitive orphan** only when the Kubernetes API can be
queried and all of the following are true:

- a ZFS filesystem exists below `cpool/k8s/csi/pvc-*`;
- no PersistentVolume using `csi.truenas.io` references that dataset as its
  `volumeHandle`;
- no VolumeAttachment references the corresponding `pvc-*` PV name.

NFS share presence is reported separately. A stale NFS share does not make the
object live; it is additional reclaim residue that must be reviewed.

If Kubernetes cannot be queried, the script reports a `CANDIDATE`, not an
`ORPHAN`. This prevents an appliance-only diagnostic from declaring storage safe
to delete without cluster correlation.

## Standard diagnostic

Run on TrueNAS from the repository worktree:

```bash
bash scripts/truenas/diagnose-csi-orphans.sh --check
```

The standard platform diagnostic also includes this check:

```bash
bash scripts/truenas/diagnose-platform.sh
```

For every dynamic `pvc-*` dataset, the diagnostic reports:

- ZFS dataset name;
- `mounted` state and configured mountpoint;
- used space;
- Kubernetes PV reference count;
- VolumeAttachment reference count;
- matching NFS share count;
- snapshot count;
- classification as `REFERENCED`, `ORPHAN`, or `CANDIDATE`.

For definitive orphans it additionally captures best-effort host and mount
namespace evidence with `findmnt`, `fuser`, `lsns`, and `nsenter` when those
tools are available. These checks are read-only.

The diagnostic deliberately states that the TrueNAS UI is not authoritative for
CSI `pvc-*` datasets.

## Manual verification for one candidate

Use this sequence before any cleanup:

```bash
PV='pvc-...'
DATASET="cpool/k8s/csi/${PV}"
PATH_="/mnt/${DATASET}"

kubectl get pv "$PV" 2>/dev/null || echo 'PV absent'

kubectl get volumeattachment -o json |
  jq --arg pv "$PV" \
    '[.items[] | select(.spec.source.persistentVolumeName == $pv)]'

sudo midclt call sharing.nfs.query |
  jq --arg p "$PATH_" \
    '[.[] | select((.path? == $p) or (((.paths? // []) | index($p)) != null))]'

sudo zfs list -H -t snapshot -r "$DATASET" || true
sudo zfs list -H -o name,type,mounted,mountpoint,used "$DATASET"
```

Then inspect local references without modifying anything:

```bash
sudo findmnt -rn -M "$PATH_" || true
sudo findmnt -rn -S "$DATASET" || true
sudo lsof +D "$PATH_" 2>/dev/null || true
sudo fuser -vm "$PATH_" || true

sudo lsns -t mnt -n -o NS,PID,COMMAND |
while read -r ns pid command; do
  mount="$(
    sudo nsenter -t "$pid" -m \
      findmnt -rn -M "$PATH_" \
      -o TARGET,SOURCE,FSTYPE 2>/dev/null || true
  )"
  if [[ -n "$mount" ]]; then
    printf 'namespace=%s pid=%s command=%s\n%s\n' \
      "$ns" "$pid" "$command" "$mount"
  fi
done
```

A `fuser` line that only shows the kernel holding the mounted parent
`/mnt/cpool/k8s/csi` is not by itself proof that the child dataset is mounted or
actively referenced.

## `EBUSY` recovery rule

If `zfs.resource.destroy` returns `EBUSY` after Kubernetes PV,
VolumeAttachment, NFS share, snapshots, and child datasets have been ruled out,
do not immediately escalate to `zfs destroy -f`.

For a planned TrueNAS reboot:

1. preserve the orphan evidence;
2. run the normal read-only reboot preflight;
3. quiesce Apps, Docker, and Talos using the controlled reboot runbook;
4. retry the supported middleware destroy after workloads are stopped if it is
   operationally useful;
5. otherwise perform the normal host reboot and re-run the orphan diagnostic
   before the post-reboot CSI regression smoke.

The goal is to distinguish a workload/mount-namespace pin from a persistent ZFS
or middleware defect without hiding the original failure.

## Cleanup acceptance

A cleanup is complete only when all relevant layers agree:

```bash
sudo zfs list "$DATASET" 2>&1 || true

sudo midclt call pool.dataset.query |
  jq --arg ds "$DATASET" '[.[] | select(.id == $ds)]'

sudo midclt call sharing.nfs.query |
  jq --arg p "/mnt/${DATASET}" \
    '[.[] | select((.path? == $p) or (((.paths? // []) | index($p)) != null))]'
```

Expected final state:

- ZFS reports that the dataset does not exist;
- middleware dataset query returns `[]`;
- NFS share query returns `[]`;
- Kubernetes has no PV or VolumeAttachment for the reclaimed volume.

Do not use the TrueNAS web UI alone as the cleanup acceptance gate.
