# TrueNAS CSI preflight

This preflight is intentionally read-only. It does not install a CSI driver,
create a StorageClass, create a Kubernetes Secret or mutate TrueNAS.

Run it after the already-operational Talos base has passed its network
regression gate. It intentionally runs **before** Kubara/Traefik and the FastAPI
external ingress smoke:

```bash
bash scripts/talos/validate-csi-prereqs.sh
```

It verifies:

- the expected Talos/Kubernetes node count;
- every node is `Ready`;
- TrueNAS TCP/2049 is reachable for the first NFS-backed storage path;
- whether the planned StorageClass already exists;
- whether any CSI drivers are already registered;
- whether `TRUENAS_CSI_API_KEY` is available without printing its value.

The planned credential must be a dedicated least-privilege TrueNAS CSI
identity. It must not reuse the OpenTofu operator identity or
`fastapi_observer`.

The first installation remains gated on a reviewed and pinned
`democratic-csi` release/chart and NFS values. TrueNAS NFSv4 is the preferred
first transport. Talos already carries its NFS client in the maintained kubelet
image, so no extra `nfs-utils` system extension is required for this path.

The storage acceptance test is independent of ingress: dynamically provision a
disposable PVC/PV, mount it from a worker, write a marker, recreate the Pod,
reschedule onto the other worker, and prove persistence before Kubara/Traefik is
introduced. The later FastAPI ingress smoke may reuse the proven StorageClass,
but it is no longer the prerequisite for CSI.
