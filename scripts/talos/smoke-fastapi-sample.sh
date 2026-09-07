#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
NAMESPACE="${K8S_FASTAPI_SMOKE_NAMESPACE:-nabla-fastapi-smoke}"
HOST="${K8S_FASTAPI_SMOKE_HOST:-test.albandrieu.com}"
INGRESS_CLASS="${K8S_FASTAPI_SMOKE_INGRESS_CLASS:-traefik}"
IMAGE="${FASTAPI_SAMPLE_K8S_IMAGE:-}"
MODE="${1:---render}"
TMPDIR_SMOKE=""

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

cleanup_tmp() {
  [[ -n "${TMPDIR_SMOKE}" ]] && rm -rf "${TMPDIR_SMOKE}"
}
trap cleanup_tmp EXIT

usage() {
  cat <<'EOF'
Usage:
  FASTAPI_SAMPLE_K8S_IMAGE=<immutable-image-ref> bash scripts/talos/smoke-fastapi-sample.sh [mode]

Modes:
  --render          render the Kubernetes manifest only (default)
  --server-dry-run  validate the manifest against the live API server without persisting it
  --apply           deploy/update the smoke workload and verify rollout + external /health
  --cleanup         delete the smoke namespace

Environment:
  KUBECONFIG                         default: .talos/generated/kubeconfig
  K8S_FASTAPI_SMOKE_NAMESPACE       default: nabla-fastapi-smoke
  K8S_FASTAPI_SMOKE_HOST            default: test.albandrieu.com
  K8S_FASTAPI_SMOKE_INGRESS_CLASS   default: traefik
  FASTAPI_SAMPLE_K8S_IMAGE           required for render/dry-run/apply
EOF
}

for command in kubectl curl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

case "${MODE}" in
  --render | --server-dry-run | --apply | --cleanup) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

if [[ "${MODE}" == "--cleanup" ]]; then
  kubectl delete namespace "${NAMESPACE}" --ignore-not-found --wait=true
  exit 0
fi

[[ -n "${IMAGE}" ]] || fail "FASTAPI_SAMPLE_K8S_IMAGE is required"
if [[ "${IMAGE}" == *":latest" ]]; then
  fail "FASTAPI_SAMPLE_K8S_IMAGE must be pinned; :latest is intentionally rejected"
fi

TMPDIR_SMOKE="$(mktemp -d)"
MANIFEST="${TMPDIR_SMOKE}/fastapi-sample-smoke.yaml"

cat >"${MANIFEST}" <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-sample
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: fastapi-sample
    app.kubernetes.io/component: smoke
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: fastapi-sample
      app.kubernetes.io/component: smoke
  template:
    metadata:
      labels:
        app.kubernetes.io/name: fastapi-sample
        app.kubernetes.io/component: smoke
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
        runAsGroup: 999
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: fastapi-sample
          image: ${IMAGE}
          imagePullPolicy: IfNotPresent
          env:
            - name: FASTAPI_ENV
              value: production
            - name: FASTAPI_RUNTIME_MODE
              value: kubernetes-smoke
            - name: FASTAPI_CLOUD
              value: ""
            - name: EXPOSE_PORT
              value: "8080"
            - name: APP_DOMAIN
              value: ${HOST}
            - name: HOMELAB_INTERNAL_PROBES_ENABLED
              value: "false"
            - name: SENTRY_ENABLED
              value: "false"
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 12
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 20
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 4
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            readOnlyRootFilesystem: false
---
apiVersion: v1
kind: Service
metadata:
  name: fastapi-sample
  namespace: ${NAMESPACE}
spec:
  selector:
    app.kubernetes.io/name: fastapi-sample
    app.kubernetes.io/component: smoke
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi-sample
  namespace: ${NAMESPACE}
spec:
  ingressClassName: ${INGRESS_CLASS}
  rules:
    - host: ${HOST}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fastapi-sample
                port:
                  name: http
EOF

case "${MODE}" in
  --render)
    cat "${MANIFEST}"
    ;;
  --server-dry-run)
    kubectl apply --dry-run=server -f "${MANIFEST}"
    ;;
  --apply)
    kubectl apply -f "${MANIFEST}"
    kubectl rollout status deployment/fastapi-sample       --namespace "${NAMESPACE}"       --timeout=180s

    endpoint_count="$(
      kubectl get endpoints fastapi-sample         --namespace "${NAMESPACE}"         -o jsonpath='{.subsets[*].addresses[*].ip}' |
        wc -w |
        tr -d ' '
    )"
    [[ "${endpoint_count}" -ge 1 ]] ||
      fail "fastapi-sample Service has no ready endpoints"

    printf '🔎 validating external FastAPI smoke: https://%s/health\n' "${HOST}"
    response="$(
      curl --fail --silent --show-error         --connect-timeout 5         --max-time 15         "https://${HOST}/health"
    )"
    [[ -n "${response}" ]] || fail "external /health returned an empty response"

    printf '✅ FastAPI Kubernetes smoke healthy: deployment, Service endpoints and https://%s/health\n' "${HOST}"
    ;;
esac
