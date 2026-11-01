#!/usr/bin/env bash
# Stop a running container by exact name, escalating from `docker stop` to
# `docker kill` and, as a last resort, to SIGKILL of its containerd shim.
set -euo pipefail

# shellcheck source=scripts/workstation/shell-status.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/scripts/workstation/shell-status.sh"

usage() {
  printf 'Usage: %s <container_name>\n' "$0"
}

# Print the full ID of the running container whose name is exactly $1.
# A substring match could select (and later SIGKILL) an unrelated container.
running_container_id() {
  docker ps --no-trunc --format '{{.ID}} {{.Names}}' |
    awk -v name="$1" '$2 == name { print $1 }'
}

case "${1:-}" in
  -h | --help)
    usage
    exit 0
    ;;
  "")
    nabla_status error "No container name provided"
    usage >&2
    exit 1
    ;;
esac
CONTAINER_NAME="$1"

CONTAINER_ID="$(running_container_id "${CONTAINER_NAME}")"
if [[ -z "${CONTAINER_ID}" ]]; then
  nabla_status error "Container '${CONTAINER_NAME}' not found in running containers"
  echo "Running containers:"
  docker ps --format "table {{.Names}}\t{{.Status}}"
  exit 1
fi

nabla_status info "Attempting to stop container '${CONTAINER_NAME}'..."
if docker stop "${CONTAINER_ID}"; then
  nabla_status ok "Successfully stopped container '${CONTAINER_NAME}'"
  exit 0
fi

nabla_status info "Docker stop failed, attempting docker kill..."
if docker kill "${CONTAINER_ID}"; then
  nabla_status ok "Successfully killed container '${CONTAINER_NAME}'"
  exit 0
fi

nabla_status info "Docker kill failed, attempting to kill containerd-shim process..."
# The shim is started with `-id <full container id>`; require exactly one match
# before sending SIGKILL so an ambiguous pattern can never kill several shims.
mapfile -t SHIM_PIDS < <(sudo pgrep -f -- "containerd-shim.* -id ${CONTAINER_ID}( |$)" || true)
if ((${#SHIM_PIDS[@]} != 1)); then
  nabla_status error "Expected exactly one containerd-shim process for ${CONTAINER_ID}, found ${#SHIM_PIDS[@]}"
  exit 1
fi

nabla_status info "Killing process ${SHIM_PIDS[0]}..."
sudo kill -9 "${SHIM_PIDS[0]}"
nabla_status info "Process killed. Checking container status..."
sleep 2
if [[ -z "$(running_container_id "${CONTAINER_NAME}")" ]]; then
  nabla_status ok "Container '${CONTAINER_NAME}' successfully stopped"
else
  nabla_status error "Container '${CONTAINER_NAME}' is still running"
  exit 1
fi
