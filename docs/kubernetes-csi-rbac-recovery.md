# TrueNAS CSI VolumeAttachment RBAC recovery

## Incident checkpoint — 2026-09-11

A disposable RWX PVC using `nabla-truenas-nfs` remained `Pending` while:

- all three Talos/Kubernetes nodes were Ready;
- cross-node DNS, ClusterIP and pod routing were healthy;
- TrueNAS NFS TCP/2049 was reachable at `172.17.0.24`;
- `cpool/k8s/csi` existed on TrueNAS, was mounted at `/mnt/cpool/k8s/csi`, and was writable;
- the TrueNAS CSI controller and node plugin were Ready;
- the CSI driver repeatedly logged successful TrueNAS pings.

The decisive evidence was in the `csi-provisioner` sidecar:

```text
volumeattachments.storage.k8s.io is forbidden:
User "system:serviceaccount:truenas-csi:truenas-csi-controller-sa"
cannot list resource "volumeattachments" in API group "storage.k8s.io"
at the cluster scope
```

The provisioner renewed its leader lease but could not fully initialize its
Kubernetes informers. During the failed provisioning window, the TrueNAS CSI
driver received health probes but no `CreateVolume` request.

## Required permission

The controller ServiceAccount needs read-only access to cluster-scoped
`VolumeAttachment` resources:

```text
apiGroup: storage.k8s.io
resource: volumeattachments
verbs: get, list, watch
```

No `create`, `update`, `patch` or `delete` permission is granted on
`VolumeAttachment` objects.

Check the effective authorization with:

```bash
kubectl auth can-i \
  --as=system:serviceaccount:truenas-csi:truenas-csi-controller-sa \
  get volumeattachments.storage.k8s.io

kubectl auth can-i \
  --as=system:serviceaccount:truenas-csi:truenas-csi-controller-sa \
  list volumeattachments.storage.k8s.io

kubectl auth can-i \
  --as=system:serviceaccount:truenas-csi:truenas-csi-controller-sa \
  watch volumeattachments.storage.k8s.io
```

All three answers must be `yes` when the driver is installed.

## Repository reconciliation

`scripts/talos/install-truenas-csi-nfs.sh --apply` now reconciles this read-only
RBAC after applying the tracked driver manifest and before waiting for the CSI
rollout. The operation is idempotent: it patches the ClusterRole only when one
of the three permissions is missing.

The tracked `kubernetes/truenas-csi/nfs-driver.yaml` also declares the same
`get/list/watch` permission, so a normal manifest reconciliation cannot remove
the runtime fix.

`scripts/talos/install-truenas-csi-nfs.sh --check` and
`scripts/talos/validate-csi-prereqs.sh` both detect an installed RBAC drift and
fail with an actionable message instead of allowing a PVC to wait until the
smoke timeout.

## Workstation versus TrueNAS filesystem checks

`/mnt/cpool/k8s/csi` is a TrueNAS appliance path. Its absence on an operator
workstation is not evidence of a missing TrueNAS dataset.

The CSI preflight therefore:

- always checks NFS TCP/2049 from the operator host;
- verifies `/mnt/cpool/k8s/csi` and `cpool/k8s/csi` directly only when `midclt`
  is available, indicating an appliance-side execution context;
- otherwise reports that dataset/mountpoint verification is skipped rather
  than failing on the workstation filesystem.

When an explicit appliance-side proof is needed from the workstation:

```bash
ssh albandrieu@172.17.0.24 \
  'zfs list cpool/k8s/csi && \
   zfs get mounted,mountpoint,readonly cpool/k8s/csi'
```

## Resume a retained failed smoke

If `CSI_SMOKE_KEEP_ON_FAILURE=true` preserved `nabla-csi-smoke`, do not create a
second PVC immediately. After fixing RBAC, first inspect whether the existing
provisioner resumes processing:

```bash
kubectl -n nabla-csi-smoke get pvc nabla-csi-rwx -w
```

Follow the sidecars without relying on a shell variable for the controller pod:

```bash
kubectl -n truenas-csi logs deployment/truenas-csi-controller \
  -c csi-provisioner --since=10m --follow
```

and, separately:

```bash
kubectl -n truenas-csi logs deployment/truenas-csi-controller \
  -c csi-controller --since=10m --follow
```

The next expected transition is `CreateVolume` reaching the TrueNAS CSI driver.
Only after the retained PVC either binds or produces the next concrete error
should the namespace be removed and the full cross-worker smoke rerun.

## Provisioning and reclaim acceptance reached

After the RBAC correction, the retained PVC resumed without recreation and
became `Bound`. Kubernetes created a CSI PV whose volume handle mapped to the
expected child dataset below `cpool/k8s/csi`.

The subsequent cleanup also proved the reclaim path:

```text
PVC/PV Bound
  -> namespace/PVC deletion
  -> PV Released
  -> external provisioner calls Controller/DeleteVolume
  -> TrueNAS CSI removes the NFS share/dataset
  -> provisioner removes its finalizer
  -> Kubernetes deletes the PV
```

The appliance-side verification confirmed that the old child dataset no longer
existed and `sharing.nfs.query` returned no matching share. This closes the
initial provisioning/RBAC blocker and proves `reclaimPolicy: Delete` for that
disposable volume.

## Pod mount/readiness timeout

The next full smoke successfully provisioned a fresh RWX PVC but the writer Pod
did not become Ready within the previous hard-coded 120 second wait. The Pod was
admitted; the `restricted:latest` PodSecurity output was a warning rather than
an admission rejection. The next diagnostic boundary is therefore Pod startup
and NFS mount readiness on the selected worker.

`scripts/talos/smoke-truenas-csi-nfs.sh` now uses:

```text
CSI_POD_READY_TIMEOUT_SECONDS=300
```

by default for writer and reader readiness. The value remains configurable for
a deliberately slower environment.

On writer or reader timeout the smoke now prints:

- Pod status and `describe` output;
- recent namespace events;
- `csi-node` logs from the exact worker selected for the Pod;
- `csi-node-driver-registrar` logs from the same worker.

When `CSI_SMOKE_KEEP_ON_FAILURE=true` is set, writer/reader failures now retain
the namespace too. Earlier behavior retained only PVC provisioning failures,
which could destroy the most useful mount-failure evidence via the exit cleanup
trap.

A deliberate slower rerun can use:

```bash
CSI_SMOKE_KEEP_ON_FAILURE=true \
CSI_PVC_TIMEOUT_SECONDS=180 \
CSI_POD_READY_TIMEOUT_SECONDS=300 \
  bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```
