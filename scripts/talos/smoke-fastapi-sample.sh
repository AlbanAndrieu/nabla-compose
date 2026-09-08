#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
NAMESPACE="${K8S_FASTAPI_SMOKE_NAMESPACE:-nabla-fastapi-smoke}"
HOST="${K8S_FASTAPI_SMOKE_HOST:-test.albandrieu.com}"
INGRESS_CLASS="${K8S_FASTAPI_SMOKE_INGRESS_CLASS:-traefik}"
API_PATH="${K8S_FASTAPI_SMOKE_API_PATH:-/v2/version}"
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
  --preflight       verify kubeconfig, IngressClass and public DNS without deployment
  --server-dry-run  validate the manifest against the live API server without persisting it
  --apply           deploy/update the smoke workload and verify rollout + public endpoints
  --cleanup         delete the smoke namespace

Environment:
  KUBECONFIG                         default: .talos/generated/kubeconfig
  K8S_FASTAPI_SMOKE_NAMESPACE       default: nabla-fastapi-smoke
  K8S_FASTAPI_SMOKE_HOST            default: test.albandrieu.com
  K8S_FASTAPI_SMOKE_INGRESS_CLASS   default: traefik
  K8S_FASTAPI_SMOKE_API_PATH        default: /v2/version
  FASTAPI_SAMPLE_K8S_IMAGE          required for render/dry-run/apply and must end in @sha256:<digest>
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

require_cluster() {
  require_command kubectl
  [[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
  export KUBECONFIG
}

resolve_public_host() {
  require_command python3
  python3 - "${HOST}" <<'PY'
import socket
import sys

host = sys.argv[1]
addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
if not addresses:
    raise SystemExit(f"no DNS address found for {host}")
print(",".join(addresses))
PY
}

check_ingress_preflight() {
  require_cluster
  require_command jq

  local ingress_controller
  ingress_controller="$(
    kubectl get ingressclass "${INGRESS_CLASS}" -o jsonpath='{.spec.controller}' 2>/dev/null
  )" || fail "IngressClass not found: ${INGRESS_CLASS}"
  [[ -n "${ingress_controller}" ]] ||
    fail "IngressClass ${INGRESS_CLASS} has no spec.controller"

  local host_claims
  host_claims="$(
    kubectl get ingress --all-namespaces -o json |
      jq -r --arg host "${HOST}" --arg namespace "${NAMESPACE}" '
        .items[]
        | select(any(.spec.rules[]?; .host == $host))
        | select(
            .metadata.namespace != $namespace
            or .metadata.name != "fastapi-sample"
          )
        | "\(.metadata.namespace)/\(.metadata.name)"
      '
  )"
  [[ -z "${host_claims}" ]] ||
    fail "Ingress host ${HOST} is already claimed by: ${host_claims}"

  local addresses
  addresses="$(resolve_public_host)" ||
    fail "public DNS lookup failed for ${HOST}"
  [[ -n "${addresses}" ]] ||
    fail "public DNS lookup returned no address for ${HOST}"

  printf '✅ ingress preflight: class=%s controller=%s host=%s addresses=%s\n' \
    "${INGRESS_CLASS}" "${ingress_controller}" "${HOST}" "${addresses}"
}

case "${MODE}" in
  --render | --preflight | --server-dry-run | --apply | --cleanup) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

if [[ "${MODE}" == "--cleanup" ]]; then
  require_cluster
  kubectl delete namespace "${NAMESPACE}" --ignore-not-found --wait=true
  exit 0
fi

if [[ "${MODE}" == "--preflight" ]]; then
  check_ingress_preflight
  exit 0
fi

[[ -n "${IMAGE}" ]] || fail "FASTAPI_SAMPLE_K8S_IMAGE is required"
if [[ ! "${IMAGE}" =~ @sha256:[0-9a-f]{64}$ ]]; then
  fail "FASTAPI_SAMPLE_K8S_IMAGE must be immutable and end in @sha256:<64-lowercase-hex-digest>"
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
    check_ingress_preflight
    kubectl apply --dry-run=server -f "${MANIFEST}"
    ;;
  --apply)
    check_ingress_preflight
    require_command curl

    kubectl apply -f "${MANIFEST}"
    kubectl rollout status deployment/fastapi-sample \
      --namespace "${NAMESPACE}" \
      --timeout=180s

    endpoint_count="$(
      kubectl get endpoints fastapi-sample \
        --namespace "${NAMESPACE}" \
        -o jsonpath='{.subsets[*].addresses[*].ip}' |
        wc -w |
        tr -d ' '
    )"
    [[ "${endpoint_count}" -ge 1 ]] ||
      fail "fastapi-sample Service has no ready endpoints"

    observed_image="$(
      kubectl get deployment fastapi-sample \
        --namespace "${NAMESPACE}" \
        -o jsonpath='{.spec.template.spec.containers[?(@.name=="fastapi-sample")].image}'
    )"
    [[ "${observed_image}" == "${IMAGE}" ]] ||
      fail "deployed image drift: expected=${IMAGE} observed=${observed_image}"

    pod_name="$(
      kubectl get pods \
        --namespace "${NAMESPACE}" \
        -l app.kubernetes.io/name=fastapi-sample,app.kubernetes.io/component=smoke \
        -o jsonpath='{.items[0].metadata.name}'
    )"
    pod_node="$(kubectl get pod "${pod_name}" --namespace "${NAMESPACE}" -o jsonpath='{.spec.nodeName}')"
    pod_ip="$(kubectl get pod "${pod_name}" --namespace "${NAMESPACE}" -o jsonpath='{.status.podIP}')"
    service_ip="$(kubectl get service fastapi-sample --namespace "${NAMESPACE}" -o jsonpath='{.spec.clusterIP}')"
    ingress_address="$(
      kubectl get ingress fastapi-sample \
        --namespace "${NAMESPACE}" \
        -o jsonpath='{range .status.loadBalancer.ingress[*]}{.ip}{.hostname}{" "}{end}' |
        xargs
    )"
    [[ -n "${ingress_address}" ]] || ingress_address="<not-published-in-status>"

    printf '🔎 correlation pod=%s node=%s pod_ip=%s service_ip=%s ingress=%s image=%s\n' \
      "${pod_name}" "${pod_node}" "${pod_ip}" "${service_ip}" "${ingress_address}" "${observed_image}"

    printf '🔎 validating external FastAPI smoke: https://%s/health\n' "${HOST}"
    health_response="$(
      curl --fail --silent --show-error \
        --connect-timeout 5 \
        --max-time 15 \
        "https://${HOST}/health"
    )"
    [[ -n "${health_response}" ]] || fail "external /health returned an empty response"

    printf '🔎 validating external FastAPI API path: https://%s%s\n' "${HOST}" "${API_PATH}"
    api_response="$(
      curl --fail --silent --show-error \
        --connect-timeout 5 \
        --max-time 15 \
        "https://${HOST}${API_PATH}"
    )"
    [[ -n "${api_response}" ]] || fail "external ${API_PATH} returned an empty response"

    printf '✅ FastAPI Kubernetes smoke healthy: rollout, Service endpoints, immutable image, /health and %s via https://%s\n' \
      "${API_PATH}" "${HOST}"
    ;;
esac
