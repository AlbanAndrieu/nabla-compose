# Kubernetes storage — TrueNAS NFS with democratic-csi

This phase adds the first persistent-storage contract after the Talos cluster, DNS, Service routing and cross-node Pod networking have been validated.

## Architecture

```text
Kubernetes PVC
    |
    v
democratic-csi nfs-client
    |
    | NFSv4.1
    v
TrueNAS 172.17.0.24:2049
    |
    v
/mnt/cpool/k8s/csi
```

TrueNAS 26 no longer provides the legacy REST API used by democratic-csi's TrueNAS-specific `freenas-*` drivers. This repository therefore uses democratic-csi's generic `nfs-client` driver and manages the NFS export separately through the `PjSalty/truenas` v2 provider, which uses the current TrueNAS JSON-RPC API.

This is intentionally a compatibility-first bootstrap. Each PVC is a directory in the shared NFS export; it is not a dedicated ZFS dataset. Native per-PVC ZFS datasets, quotas and TrueNAS snapshots should be evaluated later with the official TrueNAS CSI driver or after democratic-csi gains a supported TrueNAS 26 API path.

## Safety model

The NFS share is disabled by default. When enabled, the repository restricts it to the three Talos node addresses:

```text
172.17.0.50
172.17.0.51
172.17.0.52
```

The general `truenas-nfs` StorageClass uses `Retain`. The destructive `Delete` reclaim policy exists only on `truenas-nfs-smoke` so the acceptance test can prove deprovisioning without making application data disposable by default.

The CSI namespace is explicitly Pod Security `privileged` because the node plugin and controller-side NFS mount require mount privileges and bidirectional kubelet mount propagation. Workload smoke Pods remain in a separate namespace enforcing Pod Security `restricted`.

## 1. Review and create the TrueNAS NFS export

The dataset `/mnt/cpool/k8s/csi` already exists and remains manually owned. OpenTofu manages only the NFS share, not the dataset itself.

Start with a read-only provider plan:

```bash
export KUBERNETES_NFS_SHARE_ENABLED=true
export KUBERNETES_CSI_DATASET=k8s/csi
export KUBERNETES_NFS_ALLOWED_HOSTS=172.17.0.50,172.17.0.51,172.17.0.52
export TRUENAS_READ_ONLY=true

bash scripts/infra/preflight-truenas-talos.sh plan
scripts/infra/terragrunt-safe.sh infrastructure/truenas plan
```

The reviewed plan must add only the expected NFS share and must not change or destroy Talos VM resources.

Apply only in a supervised write window:

```bash
export TRUENAS_READ_ONLY=false
bash scripts/infra/preflight-truenas-talos.sh apply
scripts/infra/terragrunt-safe.sh infrastructure/truenas apply
```

Restore `TRUENAS_READ_ONLY=true` immediately after the apply.

## 2. Validate NFS from the Talos nodes

Before installing CSI, confirm TCP/2049 is reachable from the cluster network and the TrueNAS NFS service remains `RUNNING`. Do not broaden the share to the complete LAN to work around an authorization error; fix the explicit host list instead.

## 3. Install democratic-csi

The install helper pins chart `0.15.1` and uses the versioned values file:

```bash
mise exec -- scripts/talos/install-democratic-csi-nfs.sh
```

Expected objects include:

```text
CSIDriver      org.democratic-csi.nabla.truenas-nfs
StorageClass   truenas-nfs
StorageClass   truenas-nfs-smoke
```

No StorageClass is made the cluster default during this bootstrap. The values also disable the host `/etc/localtime` mount because Talos is an immutable OS and the CSI deployment must not depend on that host file.

The chart itself is pinned, but upstream chart `0.15.1` still defaults the democratic-csi driver image to the mutable `latest` tag. Treat the first install as a bootstrap validation: record the resolved container image digest from the healthy Pods and pin that digest in a follow-up before production workloads depend on the driver.

## 4. Prove persistence and cross-node remount

Run:

```bash
mise exec -- scripts/talos/smoke-persistent-storage.sh
```

The smoke test:

1. creates a PSA `restricted` namespace;
2. provisions a `ReadWriteMany` PVC through `truenas-nfs-smoke`;
3. writes a marker from a Pod pinned to `172.17.0.51`;
4. deletes that Pod;
5. recreates a consumer on `172.17.0.52`;
6. verifies the same marker;
7. deletes the PVC and verifies the smoke PV is deprovisioned;
8. removes the namespace automatically.

Success is reported as:

```text
✅ TrueNAS NFS persistence healthy: PVC survived cross-node Pod recreation and smoke PV cleanup succeeded
```

## Acceptance gate

Persistent storage is ready for the next phase only when all of these are true:

- TrueNAS NFS share exists with only the three Talos hosts authorized;
- democratic-csi controller and node Pods are Ready;
- both StorageClasses and the CSIDriver exist;
- the smoke PVC reaches `Bound`;
- data survives Pod deletion and cross-node recreation;
- the smoke PV is removed after the `Delete`-class PVC is deleted;
- the existing Talos cluster validator and network smoke still pass.

Only after this gate should GitOps own Kubernetes storage installation and application workloads start consuming persistent volumes.
