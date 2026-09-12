# Kubernetes FastAPI Sample smoke

This runbook uses the existing FastAPI Sample application as the explicit
Kubernetes acceptance workload behind `test.int.albandrieu.com`.

The smoke test is intentionally separate from the TrueNAS deployment behind
`sample.albandrieu.com`.

## Preconditions

1. `scripts/talos/validate-cluster.sh` is green.
2. `scripts/talos/smoke-kubernetes-network.sh` is green as a regression gate; Flannel and CoreDNS are already part of the Talos base.
3. The TrueNAS NFS + CSI gate is green: the reviewed StorageClass can dynamically bind a PVC, persist data across Pod recreation and survive rescheduling to the other worker.
4. `scripts/talos/preflight-kubara.sh --pre-bootstrap` is green with the repository pin in `config/kubara/VERSION` (`0.14.0`).
5. The target platform bootstrap is Kubara `v0.14.0`. Before installing any
   ingress controller manually, run the Kubara Helm generation flow and inspect
   the generated Traefik component. Kubara defaults `ingressClassName` to
   `traefik`; use that Kubara-managed controller unless the selected
   configuration explicitly replaces it.
6. The resulting `IngressClass` for
   `K8S_FASTAPI_SMOKE_INGRESS_CLASS` (default: `traefik`) exists and has a
   non-empty `.spec.controller`.
7. `test.int.albandrieu.com` resolves before deployment.
8. The FastAPI Sample image reference is immutable by digest. Mutable tags,
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
platform bootstrap. First require a clean, read-only pre-bootstrap state and the
exact pinned Kubara CLI contract:

```bash
bash scripts/talos/preflight-kubara.sh --pre-bootstrap
```

This gate fails if a Traefik IngressClass/controller/workload already exists or
if another Ingress already owns `test.int.albandrieu.com`. It also verifies that the
installed Kubara matches `config/kubara/VERSION` and exposes the expected
`generate --helm`, `generate --dry-run`, and `bootstrap CLUSTER_NAME` commands.

Then generate and review the platform Helm output:

```bash
kubara generate --helm
```

Inspect the generated Traefik values under
`platform-configs/<cluster>/helm/traefik/values.generated.yaml`. If Traefik is
enabled by the selected Kubara catalog/config, bootstrap/reconcile that instance
and do **not** install a second standalone Traefik chart. If Traefik is disabled,
change the Kubara configuration deliberately or select one alternative ingress
controller and update `K8S_FASTAPI_SMOKE_INGRESS_CLASS` consistently.

After the minimal Kubara platform bootstrap, rerun the read-only ownership gate:

```bash
bash scripts/talos/preflight-kubara.sh --post-bootstrap
kubectl get ingressclass
kubectl get ingressclass traefik -o yaml
```

Only continue when exactly one intended Traefik IngressClass/controller/workload
exists and its `.spec.controller` is non-empty.

Before deploying the application, verify the selected IngressClass/controller,
prove that no other Ingress already claims `test.int.albandrieu.com`, and resolve
private LAN DNS without mutating the cluster:

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
`https://test.int.albandrieu.com/health`, and the API acceptance endpoint
`https://test.int.albandrieu.com/v2/version`:

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
- existing Ingress claiming `test.int.albandrieu.com`: resolve hostname ownership
  before deploying the smoke; do not rely on controller-specific rule merging;
- private DNS lookup failure: create/reconcile the dedicated
  `test.int.albandrieu.com` LAN DNS/ingress route before application acceptance;
- network regression failure: stop before changing CSI or ingress; diagnose the already-installed CoreDNS/Flannel/Service path;
- rollout failure: inspect Pod events/logs and image compatibility;
- private `/health` or API failure with a healthy rollout: diagnose the
  ingress/edge path separately from Kubernetes workload health.

Do not use ingress to diagnose storage, and do not make CSI compensate for a
networking failure. CSI persistence must already be green before this external
ingress acceptance begins.

## Security boundary

The smoke workload:

- runs as UID/GID 999, matching the FastAPI Sample production image;
- uses the Restricted Pod Security profile;
- disables service-account token automount;
- drops Linux capabilities and forbids privilege escalation;
- disables homelab internal probes and Sentry by default;
- contains no TrueNAS, pfSense, Nexus, Vaultwarden or Cloudflare credentials;
- requires an immutable image digest for reproducible acceptance evidence.

CSI persistence is deliberately an earlier gate. This ingress smoke may mount a
disposable PVC from the already-proven TrueNAS StorageClass as an additional
end-to-end check, but CSI provisioning/persistence must not depend on
`test.int.albandrieu.com` or Traefik.
