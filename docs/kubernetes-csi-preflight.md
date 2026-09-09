# TrueNAS NFS CSI for Talos

This is the first persistent-storage implementation for the Talos cluster. It
is deliberately **NFS-only** and remains independent from Kubara/Traefik.

## Architecture decision

The repository now selects the official
`truenas/truenas-csi` driver, pinned to **v1.0.3**, rather than
`democratic-csi` for the first TrueNAS 26 path.

Reasons:

- the official driver targets TrueNAS SCALE 25.10+;
- it connects to the modern
  `wss://.../api/current` JSON-RPC/WebSocket API used by TrueNAS 26;
- NFS requires no additional Talos node package;
- the repository can remove the upstream iSCSI host mounts and
  `iscsiadm` wrapper for this NFS-only phase;
- dynamic datasets can be constrained below `cpool/k8s/csi`.

One compatibility debt remains explicit: TrueNAS CSI v1.0.3 still invokes
`auth.login_with_api_key`. That method is deprecated in TrueNAS 26. It is
acceptable only as a measured compatibility bridge on the current host and
must be replaced/upgraded to the modern username/SCRAM API-key path before
TrueNAS 27 removes the legacy method.

## Repository-owned configuration

Tracked files:

```text
kubernetes/truenas-csi/VERSION
kubernetes/truenas-csi/nfs-driver.yaml
kubernetes/truenas-csi/storageclass-nfs.yaml
scripts/talos/validate-csi-prereqs.sh
scripts/talos/install-truenas-csi-nfs.sh
scripts/talos/smoke-truenas-csi-nfs.sh
```

The current contract is:

- CSI driver: `ghcr.io/truenas/truenas-csi:v1.0.3`;
- API: `wss://truenas.albandrieu.com:7000/api/current`;
- TLS verification: enabled;
- pool: `cpool`;
- NFS server: `172.17.0.24`;
- controller/node pods pin `truenas.albandrieu.com -> 172.17.0.24` with
  `hostAliases`, preserving hostname-based TLS verification while avoiding a
  public-DNS/hairpin path through pfSense;
- provisioning parent: `cpool/k8s/csi`;
- StorageClass: `nabla-truenas-nfs`;
- NFS client mode: `hard,nfsvers=4.1`;
- the CSI node plugin is scheduled only on worker nodes; the control plane does not mount application volumes;
- allowed NFS clients: `172.17.0.51/32,172.17.0.52/32`;
- reclaim policy: `Delete`;
- the StorageClass is **not default** until persistence/reclaim acceptance is
  complete.

Snapshots and iSCSI are intentionally out of scope for this first gate.

## 0. TrueNAS operator client

Install/update the client binaries as root, but run the Kubernetes/Talos/CSI
workflow as the non-root operator `albandrieu`.

On TrueNAS as `albandrieu`:

```bash
cd /mnt/cpool/compose/nabla-compose
bash scripts/talos/configure-operator-client.sh --apply
. ~/.profile
```

Copy the existing trusted workstation configs into the **actual operator HOME**:

```text
$HOME/.config/nabla/talos/talosconfig
$HOME/.config/nabla/talos/kubeconfig
```

On this TrueNAS host, `albandrieu` currently has a persistent HOME under
`/mnt/cpool/home/albandrieu`, so do not hard-code `/home/albandrieu`.
Confirm it first with `printf '%s\n' "$HOME"` or
`getent passwd "$USER" | cut -d: -f6`.

and enforce:

```bash
chmod 700 "$HOME/.config/nabla/talos"
chmod 600 "$HOME/.config/nabla/talos/talosconfig"
chmod 600 "$HOME/.config/nabla/talos/kubeconfig"
bash scripts/talos/configure-operator-client.sh --check
```

Do not copy either file into the Git worktree and do not run the normal CSI
workflow from root. Root is reserved for TrueNAS appliance/dataset lifecycle
operations; `albandrieu` is the cluster operator.

## 1. Read-only preflight

Run after the normal Talos network regression gate:

```bash
bash scripts/talos/validate-cluster.sh
bash scripts/talos/smoke-kubernetes-network.sh
bash scripts/talos/validate-csi-prereqs.sh
```

The CSI preflight verifies:

- all three Kubernetes nodes are `Ready`;
- at least two workers exist for cross-node persistence;
- TrueNAS TCP/2049 is reachable;
- the parent mountpoint `/mnt/cpool/k8s/csi` exists;
- when the current operator can query TrueNAS datasets, `cpool/k8s/csi`
  resolves to that exact mountpoint;
- the CSI version and images are pinned;
- the tracked manifest contains no iSCSI host dependencies;
- the manifests pass `kubectl --dry-run=client`;
- existing `CSIDriver` and StorageClass ownership is surfaced before apply.

## 2. Dedicated TrueNAS CSI credential

Create a dedicated TrueNAS identity/API key for CSI. Do **not** reuse:

- `fastapi_observer`;
- the OpenTofu/Terragrunt infrastructure credential;
- an interactive human administrator key.

For the NFS-only path, use a dedicated privilege with this candidate minimum
role set:

- `POOL_READ` — the driver validates `cpool` through `pool.query`;
- `DATASET_WRITE` — create/query/get/update dynamic datasets;
- `DATASET_DELETE` — honor `reclaimPolicy: Delete`;
- `SHARING_NFS_WRITE` — create/query/get/delete the dynamic NFS shares.

Do not add iSCSI, snapshot, pool-write or full-admin roles to this first
credential. Validate these roles with the disposable PVC before promoting the
StorageClass.

The first upstream driver version consumes only the API key:

```bash
export TRUENAS_CSI_API_KEY='...'
```

Do not commit the key. The install helper creates/reconciles the Kubernetes
Secret at runtime and never prints the value.

If a dedicated username is also tracked locally, it may be exported as
`TRUENAS_CSI_API_USERNAME` for documentation/audit purposes, but v1.0.3 does
not yet consume it.

## 3. Install the NFS-only driver

First inspect without mutation:

```bash
bash scripts/talos/install-truenas-csi-nfs.sh --check
```

Then install explicitly:

```bash
TRUENAS_CSI_API_KEY='...' \
  bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

The helper:

1. creates/reconciles namespace `truenas-csi`;
2. creates `truenas-api-credentials` from the runtime key;
3. applies the NFS-only controller/node manifest;
4. waits for the controller Deployment and node DaemonSet with a bounded
   timeout (`CSI_ROLLOUT_TIMEOUT`, default `180s`); on node rollout failure,
   prints DaemonSet readiness, pod scheduling/wait reasons, recent events, and
   bounded CSI-node/registrar logs;
5. registers `csi.truenas.io`;
6. applies `nabla-truenas-nfs` only after driver readiness;
7. verifies that the StorageClass remains non-default.

## 4. Cross-worker persistence acceptance

Read-only readiness check:

```bash
bash scripts/talos/smoke-truenas-csi-nfs.sh --check
```

Disposable persistence test:

```bash
bash scripts/talos/smoke-truenas-csi-nfs.sh --apply
```

The smoke uses a BusyBox image pinned by digest by default; override
`CSI_SMOKE_IMAGE` only deliberately.

The smoke must prove:

1. a 1 GiB RWX PVC becomes `Bound`;
2. a writer Pod on worker A writes a marker;
3. that Pod is deleted;
4. a reader Pod is forced onto a different worker B;
5. the same marker is still readable;
6. the disposable namespace/PVC is deleted afterward;
7. the Kubernetes PV disappears after `DeleteVolume`;
8. the smoke prints the exact TrueNAS dataset and NFS share path that must no
   longer exist on the appliance.

Use `--keep` only when a failure needs post-mortem inspection. With
`--keep`, the script prints the exact TrueNAS dataset/share path retained for
inspection. Without `--keep`, it waits for Kubernetes PV reclaim before
success and prints the corresponding TrueNAS paths for the final appliance
verification.

## 5. Acceptance and next gate

Do not make `nabla-truenas-nfs` the default StorageClass until all of these are
green:

- driver/controller/node rollout;
- dynamic PVC provisioning;
- cross-worker persistence;
- deletion/reclaim cleanup on TrueNAS;
- one documented rollback/uninstall path.

Only then proceed to Kubara/Traefik and the immutable FastAPI smoke on
`test.albandrieu.com`.


## Runtime checkpoint · first install on TrueNAS

The first explicit install on TrueNAS reached this point:

```text
controller Deployment successfully rolled out
truenas-csi-node DaemonSet created
desired worker pods: 2
rollout status timed out after 180s
```

Kubernetes emitted a Pod Security **warning** for the node DaemonSet because a
CSI mount plugin necessarily uses host networking, hostPath mounts, root and
privileged mount operations. The workload was admitted; the timeout therefore
needs pod/event/log evidence before deciding whether the cause is image pull,
scheduling, Talos host-path/mount readiness, registration, or CSI-node startup.

Resume from this checkpoint with the improved install helper rather than
increasing the timeout blindly. A deliberate one-off longer observation can use:

```bash
CSI_ROLLOUT_TIMEOUT=300s \
  bash scripts/talos/install-truenas-csi-nfs.sh --apply
```

The helper is idempotent and will reconcile the already-created namespace,
Secret, RBAC, CSIDriver, ConfigMap, controller and node DaemonSet before
continuing to StorageClass creation.
