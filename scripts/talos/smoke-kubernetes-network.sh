#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
WORKER_A_IP="${TALOS_WORKER_A_IP:-172.17.0.51}"
WORKER_B_IP="${TALOS_WORKER_B_IP:-172.17.0.52}"
NAMESPACE="${K8S_SMOKE_NAMESPACE:-nabla-network-smoke-$$}"
IMAGE="${K8S_SMOKE_IMAGE:-busybox:1.37.0}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ "${namespace_created:-false}" == "true" ]]; then
    kubectl delete namespace "${NAMESPACE}" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for command in kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

nodes_json="$(kubectl get nodes -o json)"
node_for_ip() {
  local node_ip="$1"

  jq -r --arg ip "${node_ip}" '
    .items[]
    | select(any(.status.addresses[]?; .type == "InternalIP" and .address == $ip))
    | .metadata.name
  ' <<<"${nodes_json}"
}

worker_a_node="$(node_for_ip "${WORKER_A_IP}")"
worker_b_node="$(node_for_ip "${WORKER_B_IP}")"
[[ -n "${worker_a_node}" ]] || fail "cannot resolve Kubernetes node for ${WORKER_A_IP}"
[[ -n "${worker_b_node}" ]] || fail "cannot resolve Kubernetes node for ${WORKER_B_IP}"
[[ "${worker_a_node}" != "${worker_b_node}" ]] ||
  fail "worker IPs resolve to the same Kubernetes node: ${worker_a_node}"

printf '🔎 creating restricted smoke namespace %s\n' "${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" >/dev/null
namespace_created=true
kubectl label namespace "${NAMESPACE}" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted \
  --overwrite >/dev/null

cat <<EOF_MANIFEST | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: checker
  namespace: ${NAMESPACE}
spec:
  automountServiceAccountToken: false
  nodeName: ${worker_a_node}
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: checker
      image: ${IMAGE}
      imagePullPolicy: IfNotPresent
      command: ["sleep", "3600"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        readOnlyRootFilesystem: true
---
apiVersion: v1
kind: Pod
metadata:
  name: server-b
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: nabla-network-smoke
    app.kubernetes.io/component: server-b
spec:
  automountServiceAccountToken: false
  nodeName: ${worker_b_node}
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    fsGroup: 65532
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: server
      image: ${IMAGE}
      imagePullPolicy: IfNotPresent
      command:
        - sh
        - -c
        - 'printf "ok\\n" >/work/index.html && exec httpd -f -p 8080 -h /work'
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        httpGet:
          path: /
          port: http
        initialDelaySeconds: 1
        periodSeconds: 1
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: work
          mountPath: /work
  volumes:
    - name: work
      emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: server-b
  namespace: ${NAMESPACE}
spec:
  selector:
    app.kubernetes.io/name: nabla-network-smoke
    app.kubernetes.io/component: server-b
  ports:
    - name: http
      port: 8080
      targetPort: http
EOF_MANIFEST

kubectl wait --namespace "${NAMESPACE}" --for=condition=Ready pod/checker pod/server-b --timeout=90s >/dev/null
server_b_ip="$(kubectl get pod server-b --namespace "${NAMESPACE}" -o jsonpath='{.status.podIP}')"
[[ -n "${server_b_ip}" ]] || fail "server-b has no pod IP"

printf '🔎 validating Kubernetes DNS\n'
kubectl exec --namespace "${NAMESPACE}" checker -- \
  nslookup kubernetes.default.svc.cluster.local >/dev/null
kubectl exec --namespace "${NAMESPACE}" checker -- \
  nslookup "server-b.${NAMESPACE}.svc.cluster.local" >/dev/null

printf '🔎 validating cross-node pod routing %s -> %s\n' "${worker_a_node}" "${worker_b_node}"
direct_response="$(
  kubectl exec --namespace "${NAMESPACE}" checker -- \
    wget -qO- "http://${server_b_ip}:8080/"
)"
[[ "${direct_response}" == "ok" ]] ||
  fail "unexpected direct pod response: ${direct_response}"

printf '🔎 validating ClusterIP service routing and Service DNS\n'
service_response="$(
  kubectl exec --namespace "${NAMESPACE}" checker -- \
    wget -qO- "http://server-b.${NAMESPACE}.svc.cluster.local:8080/"
)"
[[ "${service_response}" == "ok" ]] ||
  fail "unexpected service response: ${service_response}"

printf '✅ Kubernetes network smoke healthy: DNS, Service DNS, ClusterIP and cross-node pod routing\n'
