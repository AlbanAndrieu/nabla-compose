#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TALOSCONFIG="${TALOSCONFIG:-${ROOT}/.talos/generated/talosconfig}"
KUBECONFIG="${KUBECONFIG:-${ROOT}/.talos/generated/kubeconfig}"
CONTROL_PLANE_IP="${TALOS_CONTROL_PLANE_IP:-172.17.0.50}"
EXPECTED_NODE_COUNT="${TALOS_EXPECTED_NODE_COUNT:-3}"
WORKER_IPS="${TALOS_WORKER_IPS:-172.17.0.51 172.17.0.52}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in talosctl kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${TALOSCONFIG}" ]] || fail "Talos config not found: ${TALOSCONFIG}"
[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"

export TALOSCONFIG KUBECONFIG

printf '🔎 validating Talos control plane %s\n' "${CONTROL_PLANE_IP}"
talosctl --nodes "${CONTROL_PLANE_IP}" version >/dev/null
talosctl --nodes "${CONTROL_PLANE_IP}" service etcd |
  grep -qE '^STATE[[:space:]]+Running$' || fail "etcd is not Running"
talosctl --nodes "${CONTROL_PLANE_IP}" service etcd |
  grep -qE '^HEALTH[[:space:]]+OK$' || fail "etcd health is not OK"

for worker_ip in ${WORKER_IPS}; do
  printf '🔎 validating worker %s\n' "${worker_ip}"
  talosctl --nodes "${worker_ip}" version >/dev/null
  talosctl --nodes "${worker_ip}" service kubelet |
    grep -qE '^STATE[[:space:]]+Running$' || fail "kubelet is not Running on ${worker_ip}"
  talosctl --nodes "${worker_ip}" service kubelet |
    grep -qE '^HEALTH[[:space:]]+OK$' || fail "kubelet health is not OK on ${worker_ip}"
done

nodes_json="$(kubectl get nodes -o json)"
node_count="$(jq '.items | length' <<<"${nodes_json}")"
ready_count="$(
  jq '[.items[] | select(any(.status.conditions[]; .type == "Ready" and .status == "True"))] | length'     <<<"${nodes_json}"
)"

[[ "${node_count}" -eq "${EXPECTED_NODE_COUNT}" ]] ||
  fail "expected ${EXPECTED_NODE_COUNT} Kubernetes nodes, found ${node_count}"
[[ "${ready_count}" -eq "${EXPECTED_NODE_COUNT}" ]] ||
  fail "expected ${EXPECTED_NODE_COUNT} Ready nodes, found ${ready_count}"

etcd_members="$(talosctl --nodes "${CONTROL_PLANE_IP}" etcd members --output json)"
etcd_member_count="$(jq 'length' <<<"${etcd_members}")"
[[ "${etcd_member_count}" -eq 1 ]] ||
  fail "expected exactly one etcd member for the current single-control-plane topology, found ${etcd_member_count}"

printf '✅ Talos/Kubernetes cluster healthy: %s/%s nodes Ready, etcd members=%s\n'   "${ready_count}" "${EXPECTED_NODE_COUNT}" "${etcd_member_count}"
