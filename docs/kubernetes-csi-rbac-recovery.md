# TrueNAS CSI VolumeAttachment and publishContext recovery

Last updated: 2026-09-11.

## Incident summary

The TrueNAS NFS CSI recovery has exposed three distinct layers of failure. They
must remain separate because each layer has different evidence and a different
recovery action.

1. **Provisioning RBAC** — the controller ServiceAccount could not list
   `VolumeAttachment`, so the provisioner could not fully initialize. Adding the
   required read permissions allowed the retained PVC to become `Bound`.
2. **Controller-publish contract** — the repository declared
   `CSIDriver.spec.attachRequired=false` and omitted `csi-attacher`, while
   TrueNAS CSI v1.0.3 builds the NFS connection metadata in
   `ControllerPublishVolume`. PR #187 restores that contract.
3. **Runtime credential incident during the migration rollout** — the newly
   created controller generation contained the correct attacher but its
   `csi-controller` could not authenticate to TrueNAS, so it exited before
   creating `/csi/csi.sock`. The sidecars then failed secondarily while waiting
   for that socket.

The third failure does not invalidate the `attachRequired=true` correction. It
prevented the corrected controller generation from reaching the point where
`ControllerPublishVolume` could be tested.

## First blocker — provisioning RBAC

The first decisive controller-side evidence was:

```text
volumeattachments.storage.k8s.io is forbidden:
User "system:serviceaccount:truenas-csi:truenas-csi-controller-sa"
cannot list resource "volumeattachments" in API group "storage.k8s.io"
at the cluster scope
```

Adding the required VolumeAttachment read access allowed the retained PVC to
resume without recreation and become `Bound`.

## Second blocker — empty publishContext

The writer then stayed in `ContainerCreating`, with kubelet reporting:

```text
MountVolume.MountDevice failed:
rpc error: code = InvalidArgument desc = failed to determine protocol:
unknown or missing protocol in publish context: ""
```

The node driver confirmed:

```text
NodeStageVolume received ... publishContext=null
```

TrueNAS CSI v1.0.3 uses this controller-to-node path:

```text
StorageClass protocol=nfs
  -> CreateVolume
  -> TrueNAS dataset + NFS share
  -> Kubernetes VolumeAttachment
  -> csi-attacher
  -> ControllerPublishVolume
  -> publishContext
       protocol=nfs
       nfsServer=172.17.0.24
       nfsPath=/mnt/cpool/k8s/csi/pvc-...
  -> VolumeAttachment.status.attachmentMetadata
  -> kubelet NodeStageVolume
  -> NFS mount
```

The repository had diverged from the upstream v1.0.3 contract with:

```yaml
spec:
  attachRequired: false
```

and no `csi-attacher`. Kubernetes therefore skipped the controller-publish path.
PR #187 restores:

- `CSIDriver.spec.attachRequired: true`;
- `csi-attacher:v4.11.0`;
- `get/list/watch/patch` on `volumeattachments`;
- `patch` on `volumeattachments/status`;
- no unnecessary `create/update/delete` permission for VolumeAttachment.

`CSIDriver.spec.attachRequired` is immutable. The install helper therefore
refuses to recreate the CSIDriver while TrueNAS VolumeAttachments exist, deletes
only the stale CSIDriver when safe, and reapplies the canonical object.

## Third blocker — malformed local CSI credential

During the first rollout of the corrected controller, Kubernetes correctly
created a new ReplicaSet containing `csi-attacher`, but the new Pod stayed
`1/5 CrashLoopBackOff` while the old `4/4` controller remained available.

The new `csi-attacher` repeatedly reported that `/csi/csi.sock` did not exist.
The primary failure was in the new `csi-controller`:

```text
Starting TrueNAS CSI Driver version=v1.0.3
Connecting to TrueNAS wss://truenas.albandrieu.com:7000/api/current
WebSocket connected, authenticating
TrueNAS authentication rejected
Failed to create driver: failed to connect to TrueNAS: truenas: authentication failed
```

The socket was therefore absent because the CSI driver exited before serving,
not because the `emptyDir` mount was wrong.

The local `.env.secrets` value for `TRUENAS_CSI_API_KEY` was then found to have
an erroneous extra `==` suffix. Evidence proved that the old running controller
had loaded a different credential before the Kubernetes Secret was rewritten:

```text
old running controller TRUENAS_API_KEY SHA256:
3230bacb9571e200f4927e281af935677df83ab5c9ebb718cf9dfa45bdc3a652

bad local/current Secret SHA256 observed before correction:
8eeb9e8e9208abbbc95eab6e219c8fa9d85fe37cc6366f805ae45fec2ca55dd2
```

Only fingerprints are retained; secret values must never be logged.

The corrected local key was written back to Kubernetes with the runtime-only
pipeline:

```bash
printf '%s' "${TRUENAS_CSI_API_KEY}" |
  kubectl -n truenas-csi create secret generic truenas-api-credentials \
    --from-file=api-key=/dev/stdin \
    --dry-run=client -o yaml |
  kubectl apply -f -
```

The Secret keeps its original creation timestamp but its managed field records
the correction:

```text
creationTimestamp = 2026-09-09T15:45:43Z
manager           = kubectl-client-side-apply
operation         = Update
time              = 2026-09-11T03:19:01Z
```

A Secret-backed environment variable is captured when a Pod starts. Updating
the Secret does not mutate `TRUENAS_API_KEY` inside an already-running
controller or node Pod. The CSI workloads therefore need an explicit controlled
restart/reload after a credential update.

## Credential rotation safety contract

`scripts/talos/install-truenas-csi-nfs.sh --apply` now treats credential changes
as a privileged operation:

- candidate and existing Secret values are compared only by SHA-256;
- fingerprints and secret values are not printed by the helper;
- an identical credential is idempotent;
- a differing credential is rejected by default;
- an intentional rotation requires `TRUENAS_CSI_ROTATE_CREDENTIAL=1`;
- a credential change reloads existing controller and node workloads;
- `TRUENAS_CSI_FORCE_CREDENTIAL_RELOAD=1` can reload the workloads when the
  Secret was changed out-of-band, as happened during this incident.

The guard deliberately does not claim to pre-authenticate against TrueNAS. The
upstream v1.0.3 driver still uses deprecated `auth.login_with_api_key`; runtime
controller readiness remains the authoritative authentication proof.

For this incident, after checking out the current PR #187 code and confirming
the corrected `TRUENAS_CSI_API_KEY` is loaded locally, use:

```bash
TRUENAS_CSI_FORCE_CREDENTIAL_RELOAD=1 \
TRUENAS_CSI_API_KEY="$TRUENAS_CSI_API_KEY" \
  mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

Because the corrected Secret already equals the local value, this command does
not rotate it again. It explicitly restarts the consumers so their environment
is refreshed, then waits for controller and node convergence.

For a future intentional credential replacement:

```bash
TRUENAS_CSI_ROTATE_CREDENTIAL=1 \
TRUENAS_CSI_API_KEY="$TRUENAS_CSI_API_KEY" \
  mise exec -- bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

Do not set the rotation flag simply to bypass a mismatch. First confirm that the
local secret source is the intended credential.

## Runtime convergence is part of the preflight

A correct Deployment template is not proof of a healthy CSI controller. The
read-only install/preflight gates now reject a controller when any of these is
true:

- `observedGeneration < metadata.generation`;
- updated replicas differ from desired replicas;
- ready or available replicas differ from desired replicas;
- unavailable replicas are non-zero;
- the Deployment has `Progressing=False` with
  `reason=ProgressDeadlineExceeded`.

This prevents a `1/5 CrashLoopBackOff` controller generation from being reported
as ready merely because `csi-attacher` exists in the Pod template.

## Retained runtime evidence

Do not recreate the retained smoke while the migration is being proved:

```text
PVC:    nabla-csi-rwx                       Bound
PV:     pvc-03741395-a00a-4eaf-a04e-da10e08ec530
writer: csi-writer                          ContainerCreating
target: talos-7fc-fdt
VA:     csi-2db054df7894042dbfee6309d758e9540ff5b11a2191d8316c58b3cd634a8712
state:  attached=false
```

The old controller generation lacks `csi-attacher`. The first corrected/new
generation contains all five expected containers but failed authentication with
the malformed key. After the controlled credential reload, identify the newest
controller Pod explicitly and verify it is `5/5 Running`; do not rely on
`kubectl logs deployment/...` while two generations exist.

Useful checks:

```bash
mise exec -- kubectl -n truenas-csi get deployment,rs,pod \
  -l app=truenas-csi-controller -o wide

mise exec -- kubectl -n truenas-csi get pods \
  -l app=truenas-csi-controller \
  -o custom-columns='POD:.metadata.name,CREATED:.metadata.creationTimestamp,READY:.status.containerStatuses[*].ready,CONTAINERS:.spec.containers[*].name'

mise exec -- kubectl get volumeattachment \
  csi-2db054df7894042dbfee6309d758e9540ff5b11a2191d8316c58b3cd634a8712 \
  -o yaml
```

Expected attachment state:

```yaml
status:
  attached: true
  attachmentMetadata:
    protocol: nfs
    nfsServer: 172.17.0.24
    nfsPath: /mnt/cpool/k8s/csi/pvc-...
```

## Final retained-smoke acceptance

After the corrected controller becomes healthy:

1. require the old controller generation to terminate normally;
2. require the retained VolumeAttachment to become `attached=true`;
3. require `protocol=nfs`, non-empty `nfsServer`, and non-empty `nfsPath`;
4. require `csi-writer` to become `Running` without recreating the retained PVC;
5. write the marker on worker A;
6. remove the writer;
7. schedule the reader on worker B and read the same marker;
8. delete the disposable namespace only after evidence capture;
9. require PV reclaim and automatic TrueNAS dataset/NFS-share deletion.

Then run one completely fresh smoke so acceptance covers both recovery of the
retained objects and creation of new ones:

```bash
CSI_SMOKE_KEEP_ON_FAILURE=true \
CSI_PVC_TIMEOUT_SECONDS=180 \
CSI_ATTACHMENT_TIMEOUT_SECONDS=60 \
CSI_POD_READY_TIMEOUT_SECONDS=300 \
  mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

CSI is accepted only after:

```text
Bound
+ controller runtime converged
+ attached=true
+ publishContext NFS metadata
+ cross-worker RWX
+ PV/dataset/share reclaim
+ one fresh clean smoke
```

## Reboot interaction

Do not use a TrueNAS reboot as the repair for the CSI rollout. The ordered
homelab reboot remains gated by this acceptance. If a host reboot becomes
operationally mandatory before CSI acceptance, persist the retained
Deployment/ReplicaSet/Pod/VolumeAttachment/log evidence and mark the CSI gate as
explicitly deferred. A successful post-reboot smoke is then regression evidence,
not proof of the pre-reboot failure cause.

## TrueNAS 27 compatibility debt

TrueNAS CSI v1.0.3 still authenticates through deprecated
`auth.login_with_api_key`. Keep the current TrueNAS 26 path tested and track a
supported username/SCRAM-capable driver/API path before moving to TrueNAS 27.
