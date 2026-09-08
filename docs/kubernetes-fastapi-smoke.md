# Kubernetes FastAPI Sample smoke

This runbook uses the existing FastAPI Sample application as the explicit
Kubernetes acceptance workload behind `test.albandrieu.com`.

The smoke test is intentionally separate from the TrueNAS deployment behind
`sample.albandrieu.com`.

## Preconditions

1. `scripts/talos/validate-cluster.sh` is green.
2. `scripts/talos/smoke-kubernetes-network.sh` is green.
3. An ingress controller exists for the selected
   `K8S_FASTAPI_SMOKE_INGRESS_CLASS` (default: `traefik`).
4. `test.albandrieu.com` resolves before deployment.
5. The FastAPI Sample image reference is immutable by digest. Mutable tags,
   including version tags and `:latest`, are not accepted by the smoke gate.

The FastAPI Sample repository publishes GHCR images. Supply the exact image ref:

```bash
export FASTAPI_SAMPLE_K8S_IMAGE='ghcr.io/albanandrieu/fastapi-sample@sha256:<64-lowercase-hex-digest>'
```

## Validation sequence

First retain the Talos/base-cluster gate:

```bash
bash scripts/talos/validate-cluster.sh
```

Then prove CoreDNS, Service DNS, ClusterIP routing and cross-node pod routing:

```bash
bash scripts/talos/smoke-kubernetes-network.sh
```

Before deploying the application, verify the selected IngressClass/controller,
prove that no other Ingress already claims `test.albandrieu.com`, and resolve
public DNS without mutating the cluster:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --preflight
```

The host-ownership check is deliberate: the smoke must not merge or compete
with an existing virtual-host rule. Reuse of the same hostname by a different
Ingress is treated as a configuration error before any workload is created.

Render only:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --render
```

Validate against the live Kubernetes API without persisting objects:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --server-dry-run
```

Deploy and verify rollout, Service endpoints, exact image digest,
`https://test.albandrieu.com/health`, and the API acceptance endpoint
`https://test.albandrieu.com/v2/version`:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --apply
```

The successful apply output retains correlation evidence for the selected Pod,
Kubernetes node, Pod IP, Service ClusterIP, published Ingress address when
available, and exact deployed image digest.

The API path can be overridden when the application contract changes:

```bash
K8S_FASTAPI_SMOKE_API_PATH=/api \
  bash scripts/talos/smoke-fastapi-sample.sh --apply
```

Cleanup:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --cleanup
```

## Failure interpretation

- missing/invalid `IngressClass` controller: install/configure the reviewed
  Kubernetes ingress controller before exposing the smoke workload;
- existing Ingress claiming `test.albandrieu.com`: resolve hostname ownership
  before deploying the smoke; do not rely on controller-specific rule merging;
- public DNS lookup failure: create/reconcile the dedicated
  `test.albandrieu.com` DNS/edge route before application acceptance;
- network smoke failure: stop before CSI; diagnose CoreDNS/CNI/Service routing;
- rollout failure: inspect Pod events/logs and image compatibility;
- public `/health` or API failure with a healthy rollout: diagnose the
  ingress/edge path separately from Kubernetes workload health.

Do not make CSI compensate for a networking or ingress failure.

## Security boundary

The smoke workload:

- runs as UID/GID 999, matching the FastAPI Sample production image;
- uses the Restricted Pod Security profile;
- disables service-account token automount;
- drops Linux capabilities and forbids privilege escalation;
- disables homelab internal probes and Sentry by default;
- contains no TrueNAS, pfSense, Nexus, Vaultwarden or Cloudflare credentials;
- requires an immutable image digest for reproducible acceptance evidence.

CSI persistence is deliberately a later gate. Once the complete
network/ingress smoke is green, the same workload will receive a disposable PVC
below the reviewed TrueNAS CSI StorageClass and will be used to prove
persistence across Pod recreation.
