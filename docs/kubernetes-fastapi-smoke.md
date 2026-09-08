# Kubernetes FastAPI Sample smoke

This runbook uses the existing FastAPI Sample application as the explicit
Kubernetes acceptance workload behind `test.albandrieu.com`.

The smoke test is intentionally separate from the TrueNAS deployment behind
`sample.albandrieu.com`.

## Preconditions

1. `scripts/talos/validate-cluster.sh` is green.
2. `scripts/talos/smoke-kubernetes-network.sh` is green.
3. The target platform bootstrap is Kubara `v0.14.0`. Before installing any
   ingress controller manually, run the Kubara Helm generation flow and inspect
   the generated Traefik component. Kubara defaults `ingressClassName` to
   `traefik`; use that Kubara-managed controller unless the selected
   configuration explicitly replaces it.
4. The resulting `IngressClass` for
   `K8S_FASTAPI_SMOKE_INGRESS_CLASS` (default: `traefik`) exists and has a
   non-empty `.spec.controller`.
5. `test.albandrieu.com` resolves before deployment.
6. The FastAPI Sample image reference is immutable by digest. Mutable tags,
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

The 2026-09-08 pre-platform observation is intentionally recorded as:

```text
Kubernetes: v1.36.3
Nodes:      3/3 Ready
IngressClass: none
nabla-fastapi-smoke namespace: absent
```

Talos provides the Kubernetes base here; the ingress layer is introduced by the
platform bootstrap. For the Kubara `v0.14.0` target, generate and review the
platform Helm output first:

```bash
kubara generate --helm
```

Inspect the generated Traefik values under
`platform-configs/<cluster>/helm/traefik/values.generated.yaml`. If Traefik is
enabled by the selected Kubara catalog/config, bootstrap/reconcile that instance
and do **not** install a second standalone Traefik chart. If Traefik is disabled,
change the Kubara configuration deliberately or select one alternative ingress
controller and update `K8S_FASTAPI_SMOKE_INGRESS_CLASS` consistently.

After the minimal Kubara platform bootstrap:

```bash
kubectl get ingressclass
kubectl get ingressclass traefik -o yaml
```

Only continue when one intended ingress controller exists and its
`.spec.controller` is non-empty.

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

Deploy and verify rollout, ready Service `EndpointSlice` addresses, exact image digest,
`https://test.albandrieu.com/health`, and the API acceptance endpoint
`https://test.albandrieu.com/v2/version`:

```bash
bash scripts/talos/smoke-fastapi-sample.sh --apply
```

The Service readiness gate uses `discovery.k8s.io/v1 EndpointSlice` rather than
the deprecated core `Endpoints` API. The successful apply output retains correlation evidence for the selected Pod,
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

- missing `IngressClass` before Kubara bootstrap: expected pre-platform
  state; generate/review the Kubara `v0.14.0` Helm output and reconcile the
  Kubara-managed Traefik component rather than installing a parallel controller;
- missing/invalid `IngressClass` after Kubara bootstrap: inspect the generated
  Traefik values, Argo CD application and Traefik controller before exposing
  the smoke workload;
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
