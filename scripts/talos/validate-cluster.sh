#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

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


check_node_transport() {
  local node_ip="$1"
  local role="$2"
  local route_output
  local neighbor_output
  local tcp_output

  printf '🔎 preflight %s transport %s:50000\n' "${role}" "${node_ip}"

  if ! route_output="$(ip route get "${node_ip}" 2>&1)"; then
    fail "workstation has no route to ${node_ip}: ${route_output}"
  fi
  printf '  route: %s\n' "${route_output}"

  neighbor_output="$(ip neigh show "${node_ip}" 2>/dev/null || true)"
  if [[ -n "${neighbor_output}" ]]; then
    printf '  neighbor-before: %s\n' "${neighbor_output}"
  fi

  if ! tcp_output="$(
    python3 - "${node_ip}" <<'PY'
import errno
import socket
import sys

host = sys.argv[1]
try:
    with socket.create_connection((host, 50000), timeout=2):
        print("connected")
except OSError as exc:
    name = errno.errorcode.get(exc.errno, "UNKNOWN") if exc.errno is not None else "TIMEOUT"
    print(f"{name}: errno={exc.errno} message={exc}")
    raise SystemExit(1)
PY
  )"; then
    neighbor_output="$(ip neigh show "${node_ip}" 2>/dev/null || true)"
    [[ -n "${neighbor_output}" ]] || neighbor_output="<no neighbor entry>"
    printf '  neighbor-after: %s\n' "${neighbor_output}" >&2
    printf '  tcp/50000: %s\n' "${tcp_output}" >&2
    fail "Talos API transport unavailable for ${role} ${node_ip}. Verify the TrueNAS VM is RUNNING, its IaC autostart setting is enabled and its VirtIO NIC is attached to br0. If neighbor resolution is healthy, inspect host/LAN firewall policy for TCP/50000."
  fi

  printf '  tcp/50000: %s\n' "${tcp_output}"
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

for command in talosctl kubectl jq ip python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${TALOSCONFIG}" ]] || fail "Talos config not found: ${TALOSCONFIG}"
[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"

export TALOSCONFIG KUBECONFIG

check_node_transport "${CONTROL_PLANE_IP}" "control-plane"
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
  check_node_transport "${worker_ip}" "worker"
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
