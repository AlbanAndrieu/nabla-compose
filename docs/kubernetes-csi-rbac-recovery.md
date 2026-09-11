# TrueNAS CSI VolumeAttachment and publishContext recovery

## Incident checkpoint — 2026-09-11

A disposable RWX PVC using `nabla-truenas-nfs` first remained `Pending` while:

- all three Talos/Kubernetes nodes were Ready;
- cross-node DNS, ClusterIP and pod routing were healthy;
- TrueNAS NFS TCP/2049 was reachable at `172.17.0.24`;
- `cpool/k8s/csi` existed on TrueNAS, was mounted at `/mnt/cpool/k8s/csi`, and was writable;
- the TrueNAS CSI controller and node plugin were Ready;
- the CSI driver repeatedly logged successful TrueNAS pings.

The first decisive evidence was in the `csi-provisioner` sidecar:

```text
volumeattachments.storage.k8s.io is forbidden:
User "system:serviceaccount:truenas-csi:truenas-csi-controller-sa"
cannot list resource "volumeattachments" in API group "storage.k8s.io"
at the cluster scope
```

The provisioner renewed its leader lease but could not fully initialize its
Kubernetes informers. During the failed provisioning window, the TrueNAS CSI
driver received health probes but no `CreateVolume` request.

Adding `get/list/watch` on `VolumeAttachment` fixed provisioning. The retained
PVC resumed without recreation and became `Bound`.

## Second blocker — empty publishContext

The next smoke provisioned a new RWX PVC successfully, but the writer Pod stayed
in `ContainerCreating`. Kubelet repeatedly reported:

```text
MountVolume.MountDevice failed:
rpc error: code = InvalidArgument desc = failed to determine protocol:
unknown or missing protocol in publish context: ""
```

The node driver confirmed the exact request boundary:

```text
NodeStageVolume received ... publishContext=null
```

This was not an NFS timeout, image pull problem, PodSecurity rejection, or slow
worker startup. The controller-to-node connection metadata had never been
created.

## What publishContext does

In CSI, `CreateVolume` creates/provisions the storage object. It does not by
itself provide the node with all connection details required to mount it.

For TrueNAS CSI v1.0.3, the relevant path is:

```text
StorageClass
  protocol=nfs
      |
      v
CreateVolume
  -> TrueNAS dataset + NFS share
      |
      v
VolumeAttachment created by Kubernetes
      |
      v
csi-attacher
  -> ControllerPublishVolume(volume, node)
      |
      v
publishContext
  protocol=nfs
  nfsServer=172.17.0.24
  nfsPath=/mnt/cpool/k8s/csi/pvc-...
      |
      v
VolumeAttachment.status.attachmentMetadata
      |
      v
kubelet -> NodeStageVolume
      |
      v
TrueNAS CSI node mounts NFS
```

TrueNAS CSI v1.0.3 selects its node protocol from `req.PublishContext`. For NFS,
`ControllerPublishVolume` returns at least these keys:

```text
protocol
nfsServer
nfsPath
```

If Kubernetes skips `ControllerPublishVolume`, `NodeStageVolume` receives an
empty map and cannot know whether the volume is NFS or iSCSI, nor which server
and path to mount.

## Root cause

The repository manifest had deliberately diverged from the upstream v1.0.3
contract:

```yaml
spec:
  attachRequired: false
```

and omitted the `csi-attacher` sidecar.

That combination tells Kubernetes to skip the attach/controller-publish path.
It is incompatible with TrueNAS CSI v1.0.3 because this driver uses
`ControllerPublishVolume` to build the connection metadata consumed by
`NodeStageVolume`.

The upstream v1.0.3 manifest uses:

```yaml
spec:
  attachRequired: true
```

and runs `registry.k8s.io/sig-storage/csi-attacher:v4.11.0`.

## Corrected controller contract

The canonical NFS-only deployment now restores that path:

- `CSIDriver.spec.attachRequired: true`;
- `csi-attacher:v4.11.0` in the controller Pod;
- controller RBAC `get/list/watch/patch` on `volumeattachments`;
- controller RBAC `patch` on `volumeattachments/status`.

The permission set intentionally remains narrower than the upstream all-in-one
manifest. The external-attacher needs to observe `VolumeAttachment` objects and
patch their metadata/status; Kubernetes' attach/detach controller creates the
objects. Therefore this repository does **not** add `create`, `update` or
`delete` on `VolumeAttachment` for the TrueNAS controller ServiceAccount.

Effective checks:

```bash
for verb in get list watch patch; do
  kubectl auth can-i \
    --as=system:serviceaccount:truenas-csi:truenas-csi-controller-sa \
    "${verb}" volumeattachments.storage.k8s.io
done

kubectl auth can-i \
  --as=system:serviceaccount:truenas-csi:truenas-csi-controller-sa \
  patch volumeattachments.storage.k8s.io --subresource=status
```

All answers must be `yes`.

## One-time migration of attachRequired

`CSIDriver.spec.attachRequired` is immutable. An installed object with
`attachRequired=false` cannot be converted in place by `kubectl apply`.

`scripts/talos/install-truenas-csi-nfs.sh --apply` therefore:

1. detects the old value;
2. refuses to recreate the CSIDriver while any TrueNAS `VolumeAttachment`
   exists;
3. deletes only the stale `CSIDriver` object;
4. reapplies the canonical manifest with `attachRequired=true`;
5. verifies the attacher and effective RBAC before accepting the rollout.

The driver Deployment, DaemonSet, StorageClass, Secret and TrueNAS datasets are
not deleted by this metadata migration.

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

## Provisioning and reclaim acceptance reached

After the first RBAC correction, the retained PVC resumed without recreation
and became `Bound`. Kubernetes created a CSI PV whose volume handle mapped to
the expected child dataset below `cpool/k8s/csi`.

The subsequent cleanup proved the reclaim path:

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
existed and `sharing.nfs.query` returned no matching share.

## Fail-fast smoke diagnostics

The persistence smoke now validates the attach contract before creating any
resource. It refuses to run when either:

- `CSIDriver.spec.attachRequired != true`; or
- the controller Deployment has no `csi-attacher` container.

After scheduling each writer/reader Pod it waits separately for the matching
`VolumeAttachment` and requires, within `CSI_ATTACHMENT_TIMEOUT_SECONDS`
(default `60` seconds):

```text
status.attached = true
status.attachmentMetadata.protocol = nfs
status.attachmentMetadata.nfsServer != empty
status.attachmentMetadata.nfsPath != empty
```

Only after that control-plane contract is proven does the longer Pod Ready
wait begin. A missing publish context therefore fails in roughly one minute
instead of consuming the full Pod readiness timeout.

On failure the smoke prints the matching `VolumeAttachment`, its attach error,
`csi-attacher` logs and TrueNAS `csi-controller` logs.

## Acceptance sequence

After deploying this change, use:

```bash
mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --check
```

The currently installed `attachRequired=false` object is expected to fail this
read-only check until migrated. Then apply the one-time correction:

```bash
TRUENAS_CSI_API_KEY="$TRUENAS_CSI_API_KEY" \
  mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

Re-run the preflight and smoke:

```bash
mise exec -- bash scripts/talos/validate-csi-prereqs.sh

CSI_SMOKE_KEEP_ON_FAILURE=true \
CSI_PVC_TIMEOUT_SECONDS=180 \
CSI_ATTACHMENT_TIMEOUT_SECONDS=60 \
CSI_POD_READY_TIMEOUT_SECONDS=300 \
  mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

Expected evidence before the writer becomes Ready:

```text
✅ publishContext ready for <writer>:
   protocol=nfs server=172.17.0.24 path=/mnt/cpool/k8s/csi/pvc-...
```

The final acceptance remains: writer on one worker, reader on the other worker,
same marker, then successful PV/TrueNAS dataset/share reclaim.
