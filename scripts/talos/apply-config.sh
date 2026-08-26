#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(git rev-parse --show-toplevel)"
OUTPUT_DIR="${TALOS_OUTPUT_DIR:-${ROOT}/.talos/generated}"
CLUSTER_NAME="${TALOS_CLUSTER_NAME:-nabla-talos}"
INSTALL_DISK="${TALOS_INSTALL_DISK:-/dev/vda}"
ALLOW_APPLY="${TALOS_APPLY_CONFIG:-false}"
DISK_VERIFIED="${TALOS_DISK_VERIFIED:-false}"
CONFIRM_CLUSTER="${TALOS_CONFIRM_CLUSTER:-}"

CONTROL_PLANE_CONFIG="${OUTPUT_DIR}/controlplane.yaml"
WORKER_CONFIG="${OUTPUT_DIR}/worker.yaml"

control_planes=()
workers=()

die() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  scripts/talos/apply-config.sh \
    --control-plane <IPv4> [--control-plane <IPv4> ...] \
    [--worker <IPv4> ...]

Default behavior is preflight-only. It validates the generated Talos configs and
queries disks from each node in maintenance mode without applying configuration.

To permit apply-config, all of these must be set deliberately:
  TALOS_APPLY_CONFIG=true
  TALOS_DISK_VERIFIED=true
  TALOS_CONFIRM_CLUSTER=<exact TALOS_CLUSTER_NAME>

This script never runs `talosctl bootstrap`.
EOF
}

is_ipv4() {
  local ip="$1" octet
  local -a octets
  IFS='.' read -r -a octets <<<"${ip}"
  ((${#octets[@]} == 4)) || return 1
  for octet in "${octets[@]}"; do
    [[ "${octet}" =~ ^[0-9]{1,3}$ ]] || return 1
    ((10#${octet} <= 255)) || return 1
  done
}

while (($# > 0)); do
  case "$1" in
    --control-plane)
      (($# >= 2)) || die "--control-plane requires an IPv4 address"
      control_planes+=("$2")
      shift 2
      ;;
    --worker)
      (($# >= 2)) || die "--worker requires an IPv4 address"
      workers+=("$2")
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

command -v talosctl >/dev/null 2>&1 || die "talosctl is required"
[[ -f "${CONTROL_PLANE_CONFIG}" ]] || die "missing ${CONTROL_PLANE_CONFIG}; run scripts/talos/generate-config.sh first"
[[ -f "${WORKER_CONFIG}" ]] || die "missing ${WORKER_CONFIG}; run scripts/talos/generate-config.sh first"
[[ "${INSTALL_DISK}" == /dev/* ]] || die "TALOS_INSTALL_DISK must be an absolute /dev path"
[[ "${ALLOW_APPLY}" == "true" || "${ALLOW_APPLY}" == "false" ]] || die "TALOS_APPLY_CONFIG must be true or false"
[[ "${DISK_VERIFIED}" == "true" || "${DISK_VERIFIED}" == "false" ]] || die "TALOS_DISK_VERIFIED must be true or false"
((${#control_planes[@]} > 0)) || die "at least one --control-plane node is required"

all_nodes=("${control_planes[@]}" "${workers[@]}")
declare -A seen_nodes=()
for node in "${all_nodes[@]}"; do
  is_ipv4 "${node}" || die "invalid IPv4 node address: ${node}"
  [[ -z "${seen_nodes[${node}]:-}" ]] || die "duplicate node address: ${node}"
  seen_nodes["${node}"]=1
done

printf '✅ Validating generated Talos machine configurations...\n'
talosctl validate --config "${CONTROL_PLANE_CONFIG}" --mode metal --strict
talosctl validate --config "${WORKER_CONFIG}" --mode metal --strict

printf '🔎 Inspecting maintenance-mode disks on all requested nodes...\n'
for node in "${all_nodes[@]}"; do
  printf '\n--- node %s ---\n' "${node}"
  talosctl get disks --insecure --nodes "${node}"
done

cat <<EOF

Expected install disk from generated configuration: ${INSTALL_DISK}
Verify the output above against the TrueNAS zvol-backed VirtIO disk before enabling writes.
EOF

if [[ "${ALLOW_APPLY}" != "true" ]]; then
  cat <<'EOF'

✅ Preflight complete. No configuration was applied.
Set the three explicit safety acknowledgements shown by --help only after node IPs
and install disks have been verified.
EOF
  exit 0
fi

[[ "${DISK_VERIFIED}" == "true" ]] || die "refusing apply: TALOS_DISK_VERIFIED=true is required"
[[ "${CONFIRM_CLUSTER}" == "${CLUSTER_NAME}" ]] || die "refusing apply: TALOS_CONFIRM_CLUSTER must exactly equal ${CLUSTER_NAME}"

printf '⚠️  Applying control-plane configuration to %d node(s)...\n' "${#control_planes[@]}"
for node in "${control_planes[@]}"; do
  talosctl apply-config --insecure --nodes "${node}" --file "${CONTROL_PLANE_CONFIG}"
done

if ((${#workers[@]} > 0)); then
  printf '⚠️  Applying worker configuration to %d node(s)...\n' "${#workers[@]}"
  for node in "${workers[@]}"; do
    talosctl apply-config --insecure --nodes "${node}" --file "${WORKER_CONFIG}"
  done
fi

cat <<'EOF'

✅ Requested machine configurations were submitted.
No etcd/Kubernetes bootstrap was performed. Bootstrap remains a separate,
one-time operation against exactly one control-plane node after node health is reviewed.
EOF
