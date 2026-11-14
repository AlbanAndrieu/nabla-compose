#!/usr/bin/env bash
# Narrow, read-only execution-mode router. No LAN probe unless explicitly opted in.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${AGENT_EXECUTION_MODE:-offline}"
action="static"
services=()
while (($#)); do
  case "$1" in
    --mode) [[ $# -ge 2 ]] || { echo 'ERROR: --mode requires offline|workstation' >&2; exit 2; }; mode="$2"; shift ;;
    --static) action=static ;;
    --runtime) action=runtime ;;
    --help|-h)
      echo "Usage: $0 [--mode offline|workstation] [--static | --runtime service [service...]]"
      echo 'Default is offline; runtime requires explicit workstation mode and named services.'
      exit 0 ;;
    --*) echo "ERROR: invalid option $1" >&2; exit 2 ;;
    *) services+=("$1") ;;
  esac
  shift
done
[[ "$mode" == offline || "$mode" == workstation ]] || {
  echo 'ERROR: AGENT_EXECUTION_MODE must be offline or workstation' >&2; exit 2;
}
if [[ "$action" == static ]]; then
  (("${#services[@]}" == 0)) || { echo 'ERROR: services require --runtime' >&2; exit 2; }
  exec bash "$root/scripts/agent-offline-check.sh"
fi
if [[ "$mode" != workstation ]]; then
  echo 'NOT_RUN: LAN/runtime diagnostics require explicit workstation mode' >&2
  exit 2
fi
(("${#services[@]}" > 0 && "${#services[@]}" <= 3)) || {
  echo 'ERROR: --runtime requires 1..3 service IDs' >&2; exit 2;
}
for service in "${services[@]}"; do
  [[ "$service" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || {
    echo 'ERROR: invalid service ID' >&2; exit 2;
  }
done
exec python3 "$root/scripts/truenas/verify-service-observability.py" "${services[@]}"
