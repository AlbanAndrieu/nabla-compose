# TrueNAS CSI preflight

This preflight is intentionally read-only. It does not install a CSI driver,
create a StorageClass, create a Kubernetes Secret or mutate TrueNAS.

Run it only after the Kubernetes DNS/CNI and FastAPI Sample smoke gates are
green:

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

The first installation remains gated on a reviewed driver/chart version and
values file. The first acceptance test will create a disposable PVC, write a
marker, recreate the FastAPI Sample smoke pod and prove persistence through
`test.albandrieu.com`.
