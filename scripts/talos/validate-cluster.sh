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

check_kubelet() {
  local node_ip="$1"
  talosctl --nodes "${node_ip}" service kubelet |
    grep -qE '^STATE[[:space:]]+Running$' ||
    fail "kubelet is not Running on ${node_ip}"
  talosctl --nodes "${node_ip}" service kubelet |
    grep -qE '^HEALTH[[:space:]]+OK$' ||
    fail "kubelet health is not OK on ${node_ip}"
}

count_etcd_members() {
  local members_output="$1"

  awk '
    BEGIN {
      header_seen = 0
      malformed = 0
    }
    /^NODE[[:space:]]+ID[[:space:]]+HOSTNAME([[:space:]]|$)/ {
      header_seen = 1
      next
    }
    header_seen && NF && $NF ~ /^(true|false)$/ {
      member_ids[$2] = 1
      next
    }
    header_seen && NF {
      malformed = 1
    }
    END {
      if (!header_seen || malformed) {
        exit 2
      }

      count = 0
      for (id in member_ids) {
        count++
      }
      print count
    }
  ' <<<"${members_output}"
}

for command in talosctl kubectl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${TALOSCONFIG}" ]] || fail "Talos config not found: ${TALOSCONFIG}"
[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"

export TALOSCONFIG KUBECONFIG

printf '🔎 validating Talos control plane %s\n' "${CONTROL_PLANE_IP}"
talosctl --nodes "${CONTROL_PLANE_IP}" version >/dev/null
check_kubelet "${CONTROL_PLANE_IP}"

talosctl --nodes "${CONTROL_PLANE_IP}" service etcd |
  grep -qE '^STATE[[:space:]]+Running$' || fail "etcd is not Running"
talosctl --nodes "${CONTROL_PLANE_IP}" service etcd |
  grep -qE '^HEALTH[[:space:]]+OK$' || fail "etcd health is not OK"
talosctl --nodes "${CONTROL_PLANE_IP}" etcd status >/dev/null ||
  fail "etcd status is unavailable"

# /var is backed by Talos EPHEMERAL storage. This checks that usage telemetry is
# readable on every node; hard free-space thresholds are added via metrics once
# the node metric path is deployed.
talosctl --nodes "${CONTROL_PLANE_IP}" usage /var -H >/dev/null ||
  fail "cannot read /var usage on ${CONTROL_PLANE_IP}"

for worker_ip in ${WORKER_IPS}; do
  printf '🔎 validating worker %s\n' "${worker_ip}"
  talosctl --nodes "${worker_ip}" version >/dev/null
  check_kubelet "${worker_ip}"
  talosctl --nodes "${worker_ip}" usage /var -H >/dev/null ||
    fail "cannot read /var usage on ${worker_ip}"
done

kubectl get --raw='/readyz' >/dev/null ||
  fail "Kubernetes API readyz failed"

nodes_json="$(kubectl get nodes -o json)"
node_count="$(jq '.items | length' <<<"${nodes_json}")"
ready_count="$(
  jq '[.items[] | select(any(.status.conditions[]; .type == "Ready" and .status == "True"))] | length' <<<"${nodes_json}"
)"

[[ "${node_count}" -eq "${EXPECTED_NODE_COUNT}" ]] ||
  fail "expected ${EXPECTED_NODE_COUNT} Kubernetes nodes, found ${node_count}"
[[ "${ready_count}" -eq "${EXPECTED_NODE_COUNT}" ]] ||
  fail "expected ${EXPECTED_NODE_COUNT} Ready nodes, found ${ready_count}"

pressure_summary="$(
  jq -r '
    [
      .items[] as $node
      | $node.status.conditions[]
      | select(
          (
            .type == "DiskPressure"
            or .type == "MemoryPressure"
            or .type == "PIDPressure"
            or .type == "NetworkUnavailable"
          )
          and .status == "True"
        )
      | "\($node.metadata.name):\(.type)"
    ]
    | join(", ")
  ' <<<"${nodes_json}"
)"
[[ -z "${pressure_summary}" ]] ||
  fail "Kubernetes node pressure detected: ${pressure_summary}"

etcd_members_output="$(talosctl --nodes "${CONTROL_PLANE_IP}" etcd members)"
etcd_member_count="$(count_etcd_members "${etcd_members_output}")" ||
  fail "unexpected talosctl etcd members table format"
[[ "${etcd_member_count}" -eq 1 ]] ||
  fail "expected exactly one etcd member for the current single-control-plane topology, found ${etcd_member_count}"

printf '✅ Talos/Kubernetes cluster healthy: %s/%s nodes Ready, etcd members=%s, node pressure=none\n' \
  "${ready_count}" "${EXPECTED_NODE_COUNT}" "${etcd_member_count}"
