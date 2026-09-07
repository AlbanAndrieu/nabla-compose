# Kubernetes FastAPI Sample smoke

This directory/runbook stage uses the existing FastAPI Sample application as the
explicit Kubernetes acceptance workload behind `test.albandrieu.com`.

The smoke test is intentionally separate from the TrueNAS deployment behind
`sample.albandrieu.com`.

## Preconditions

1. `scripts/talos/validate-cluster.sh` is green.
2. `scripts/talos/smoke-kubernetes-network.sh` is green.
3. An ingress controller exists for the selected
   `K8S_FASTAPI_SMOKE_INGRESS_CLASS` (default: `traefik`).
4. `test.albandrieu.com` resolves to the ingress path selected for the cluster.
5. The FastAPI Sample image reference is immutable/pinned. The smoke helper
   rejects `:latest`.

The FastAPI Sample repository publishes GHCR images. Supply the exact image ref:

```bash
export FASTAPI_SAMPLE_K8S_IMAGE='ghcr.io/albanandrieu/fastapi-sample@sha256:<digest>'
```

## Validation sequence

Render only:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --render
```

Validate against the live Kubernetes API without persisting objects:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --server-dry-run
```

Deploy and verify rollout, Service endpoints and the public health path:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --apply
```

Cleanup:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --cleanup
```

## Security boundary

The smoke workload:

- runs as UID/GID 999, matching the FastAPI Sample production image;
- uses the Restricted Pod Security profile;
- disables service-account token automount;
- drops Linux capabilities and forbids privilege escalation;
- disables homelab internal probes and Sentry by default;
- contains no TrueNAS, pfSense, Nexus, Vaultwarden or Cloudflare credentials.

CSI persistence is deliberately a later gate. Once the network/ingress smoke is
green, the same workload will receive a disposable PVC below the reviewed
TrueNAS CSI StorageClass and will be used to prove persistence across pod
recreation.
