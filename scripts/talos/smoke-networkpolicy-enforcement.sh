#!/usr/bin/env bash
set -euo pipefail

# Shared compact/full diagnostic bootstrap.
NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/diagnostic.sh
source "$(dirname -- "${NABLA_SCRIPT_DIR}")/lib/diagnostic.sh"
nabla_diagnostic_maybe_wrap "${BASH_SOURCE[0]}" "$@"

# Proves that Kubernetes NetworkPolicy is actually enforced by the cluster CNI,
# with positive and negative cross-node probes for both ingress and egress.
# Exit 0 only when every allowed flow passes and every denied flow is blocked.
# A CNI that silently accepts NetworkPolicy objects without enforcing them
# fails this smoke. Everything lives in a disposable namespace.

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
WORKER_A_IP="${TALOS_WORKER_A_IP:-172.17.0.51}"
WORKER_B_IP="${TALOS_WORKER_B_IP:-172.17.0.52}"
NAMESPACE="${K8S_SMOKE_NAMESPACE:-nabla-netpol-smoke-$$}"
IMAGE="${K8S_SMOKE_IMAGE:-busybox:1.37.0}"
POLICY_WAIT_SECONDS="${K8S_POLICY_WAIT_SECONDS:-30}"
PROBE_TIMEOUT_SECONDS=3

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

cleanup() {
  if [[ "${namespace_created:-false}" == "true" ]]; then
    kubectl delete namespace "${NAMESPACE}" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

require_commands kubectl jq

[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG
[[ "${POLICY_WAIT_SECONDS}" =~ ^[0-9]+$ ]] ||
  fail "K8S_POLICY_WAIT_SECONDS must be a non-negative integer"

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

# Restricted, non-root pod; servers run busybox httpd on 8080.
pod_manifest() {
  local name="$1" node="$2" role="$3" serve="$4"
  local command='["sleep", "3600"]'

  if [[ "${serve}" == "true" ]]; then
    command='["sh", "-c", "mkdir -p /tmp/www && printf ok >/tmp/www/index.html && exec httpd -f -p 8080 -h /tmp/www"]'
  fi

  cat <<EOF_POD
---
apiVersion: v1
kind: Pod
metadata:
  name: ${name}
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: nabla-netpol-smoke
    nabla.io/netpol-role: ${role}
spec:
  automountServiceAccountToken: false
  nodeName: ${node}
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: main
      image: ${IMAGE}
      imagePullPolicy: IfNotPresent
      command: ${command}
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir: {}
EOF_POD
}

# probe CLIENT IP -> 0 when HTTP 8080 answers "ok", 1 otherwise.
probe() {
  local client="$1" target_ip="$2" body

  body="$(
    kubectl exec --namespace "${NAMESPACE}" "${client}" -- \
      wget -qO- -T "${PROBE_TIMEOUT_SECONDS}" "http://${target_ip}:8080/" 2>/dev/null
  )" || return 1
  [[ "${body}" == "ok" ]]
}

# expect_flow CLIENT IP allowed|blocked LABEL: retries until the policy
# converges or POLICY_WAIT_SECONDS elapses.
expect_flow() {
  local client="$1" target_ip="$2" expected="$3" label="$4"
  local deadline=$((SECONDS + POLICY_WAIT_SECONDS)) observed

  while :; do
    if probe "${client}" "${target_ip}"; then
      observed=allowed
    else
      observed=blocked
    fi
    if [[ "${observed}" == "${expected}" ]]; then
      ok "${label}: ${observed}"
      return 0
    fi
    ((SECONDS < deadline)) || break
    sleep 2
  done

  if [[ "${expected}" == "blocked" ]]; then
    fail "${label}: still allowed after ${POLICY_WAIT_SECONDS}s — NetworkPolicy is NOT enforced by this CNI"
  fi
  fail "${label}: expected allowed, observed blocked"
}

section "Creating restricted smoke namespace ${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" >/dev/null
namespace_created=true
kubectl label namespace "${NAMESPACE}" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted \
  --overwrite >/dev/null

{
  pod_manifest client-allowed "${worker_a_node}" client-allowed false
  pod_manifest client-denied "${worker_a_node}" client-denied false
  pod_manifest server-guarded "${worker_b_node}" server-guarded true
  pod_manifest server-open "${worker_b_node}" server-open true
} | kubectl apply -f - >/dev/null

kubectl wait --namespace "${NAMESPACE}" --for=condition=Ready \
  pod/client-allowed pod/client-denied pod/server-guarded pod/server-open \
  --timeout=90s >/dev/null

guarded_ip="$(kubectl get pod server-guarded --namespace "${NAMESPACE}" -o jsonpath='{.status.podIP}')"
open_ip="$(kubectl get pod server-open --namespace "${NAMESPACE}" -o jsonpath='{.status.podIP}')"
[[ -n "${guarded_ip}" && -n "${open_ip}" ]] || fail "server pods have no pod IP"

# Without a working baseline a "blocked" result would prove nothing.
section "Baseline without policy (${worker_a_node} -> ${worker_b_node})"
for client in client-allowed client-denied; do
  for target in "${guarded_ip}" "${open_ip}"; do
    probe "${client}" "${target}" ||
      fail "baseline ${client} -> ${target} failed; inconclusive, run smoke-kubernetes-network.sh first"
  done
done
ok "baseline: all four cross-node flows reachable"

section "Ingress policy: only client-allowed may reach server-guarded"
cat <<EOF_POLICY | kubectl apply -f - >/dev/null
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: server-guarded-ingress-allowlist
  namespace: ${NAMESPACE}
spec:
  podSelector:
    matchLabels:
      nabla.io/netpol-role: server-guarded
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              nabla.io/netpol-role: client-allowed
      ports:
        - protocol: TCP
          port: 8080
EOF_POLICY
expect_flow client-denied "${guarded_ip}" blocked "ingress client-denied -> server-guarded"
expect_flow client-allowed "${guarded_ip}" allowed "ingress client-allowed -> server-guarded"

section "Egress policy: client-denied keeps DNS only"
cat <<EOF_POLICY | kubectl apply -f - >/dev/null
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: client-denied-egress-dns-only
  namespace: ${NAMESPACE}
spec:
  podSelector:
    matchLabels:
      nabla.io/netpol-role: client-denied
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
EOF_POLICY
expect_flow client-denied "${open_ip}" blocked "egress client-denied -> server-open"
expect_flow client-allowed "${open_ip}" allowed "egress client-allowed -> server-open"
kubectl exec --namespace "${NAMESPACE}" client-denied -- \
  nslookup kubernetes.default.svc.cluster.local >/dev/null ||
  fail "egress DNS allowlist broke cluster DNS for client-denied"
ok "egress client-denied -> kube-dns: allowed"

ok "NetworkPolicy enforced: ingress and egress allow/deny proven cross-node"
