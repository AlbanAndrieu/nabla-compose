#!/usr/bin/env bash
# Standalone read-only homelab health diagnostic; no reboot manifest required.
set -uo pipefail
DEEP=false
VERBOSE=false
for arg in "$@"; do
  case "$arg" in
    --deep) DEEP=true ;;
    --verbose) VERBOSE=true ;;
    *) printf 'usage: %s [--deep] [--verbose]\n' "$0" >&2; exit 2 ;;
  esac
done
GREEN='' RED='' YELLOW='' RESET=''
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  GREEN="$(printf '\033[32m')"
  RED="$(printf '\033[31m')"
  YELLOW="$(printf '\033[33m')"
  RESET="$(printf '\033[0m')"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
failed=0
warnings=0

run_gate() {
  local name="$1"
  shift
  if "$@" >"${runtime_tmp}/${name}.log" 2>&1; then
    [[ "$VERBOSE" == true ]] && cat "${runtime_tmp}/${name}.log"
    printf '%s✅ PASS %s%s\n' "${GREEN}" "$name" "${RESET}"
  else
    printf '%s❌ FAIL %s%s\n' "${RED}" "$name" "${RESET}"
    tail -n 12 "${runtime_tmp}/${name}.log"
    failed=$((failed + 1))
  fi
}

if ! command -v midclt >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  echo 'ERROR: this diagnostic requires TrueNAS midclt and jq' >&2
  exit 2
fi

printf '🏠 Homelab health · topology-ordered checks\n'
apps_json="$(midclt call app.query)" || { echo 'FAIL app.query'; exit 2; }
if [[ "$DEEP" == true ]]; then
  echo '🔗 Deep probes enabled'
fi
runtime_tmp="$(mktemp -d)"
trap 'rm -f "${runtime_tmp}"/apps.json "${runtime_tmp}"/plan.json "${runtime_tmp}"/*.log; rmdir "${runtime_tmp}" 2>/dev/null || true' EXIT
printf '%s\n' "$apps_json" >"${runtime_tmp}/apps.json"
if python3 "${ROOT}/scripts/truenas/plan-app-lifecycle-order.py" \
  --apps "${runtime_tmp}/apps.json" --states RUNNING,DEPLOYING,CRASHED,ERROR \
  --services "${ROOT}/catalog/services.json" \
  --topology "${ROOT}/catalog/service-topology.json" \
  >"${runtime_tmp}/plan.json"; then
  extra=()
  [[ "$DEEP" == true ]] && extra+=(--deep)
  [[ "$VERBOSE" == true ]] && extra+=(--verbose)
  python3 "${ROOT}/scripts/truenas/audit-homelab-service-dependencies.py" \
    --apps "${runtime_tmp}/apps.json" --plan "${runtime_tmp}/plan.json" "${extra[@]}" || failed=$((failed + 1))
else
  echo '❌ FAIL dependency plan unavailable'
  failed=$((failed + 1))
fi
unhealthy="$(jq -r '[.[] | select(.state == "CRASHED" or .state == "ERROR")] | length' <<<"$apps_json")"
if ((unhealthy > 0)); then
  printf 'FAIL %d TrueNAS Apps in CRASHED/ERROR state\n' "$unhealthy"
  failed=$((failed + 1))
fi

printf '\n🐳 Docker container health\n'
if command -v docker >/dev/null 2>&1; then
  [[ "$VERBOSE" == true ]] && docker ps --format '{{.Names}}\t{{.Status}}'
  unhealthy_containers="$(docker ps --format '{{.Names}} {{.Status}}' | grep -Ei 'unhealthy|restarting' || true)"
  # Do not mistake a healthy TrueNAS App for healthy auxiliary containers.
  # Docker ps excludes exited Compose services, including bitwarden-api.
  exited_critical="$(docker ps -a --filter 'name=^/bitwarden-api
    printf '%s\n' "$unhealthy_containers"
    printf '%s❌ FAIL Docker unhealthy/restarting containers detected%s\n' "$RED" "$RESET"
    failed=$((failed + 1))
  fi
else
  echo 'WARN Docker CLI unavailable'
  warnings=$((warnings + 1))
fi

if jq -e '.[] | select(.id == "dsomm" and .state == "RUNNING")' <<<"$apps_json" >/dev/null; then
  run_gate dsomm python3 "${ROOT}/scripts/truenas/check-dsomm-post-reboot.py"
else
  echo 'WARN DSOMM not RUNNING; skipping DSOMM check'
  warnings=$((warnings + 1))
fi

if [[ -f "${ROOT}/scripts/truenas/diagnose-fastapi-integrations.py" ]]; then
  run_gate fastapi-integrations python3 "${ROOT}/scripts/truenas/diagnose-fastapi-integrations.py"
else
  echo 'WARN FastAPI diagnostic unavailable'
  warnings=$((warnings + 1))
fi

if [[ -f "${ROOT}/scripts/ingress/audit-internal-routes.py" ]]; then
  run_gate ingress-routes python3 "${ROOT}/scripts/ingress/audit-internal-routes.py" --strict
else
  printf '%s⚠️ WARN ingress audit unavailable%s\n' "$YELLOW" "$RESET"
  warnings=$((warnings + 1))
fi

printf '\n📊 Homelab result: failures=%d warnings=%d\n' "$failed" "$warnings"
((failed == 0))
 \
    --filter 'status=exited' --format '{{.Names}} {{.Status}}' || true)"
  if [[ -n "$exited_critical" ]]; then
    printf '%s⚠️ WARN Vaultwarden legacy adapter stopped: %s%s\n' \
      "$YELLOW" "$exited_critical" "$RESET"
    warnings=$((warnings + 1))
  fi
  if [[ -n "$unhealthy_containers" ]]; then
    printf '%s\n' "$unhealthy_containers"
    printf '%s❌ FAIL Docker unhealthy/restarting containers detected%s\n' "$RED" "$RESET"
    failed=$((failed + 1))
  fi
else
  echo 'WARN Docker CLI unavailable'
  warnings=$((warnings + 1))
fi

if jq -e '.[] | select(.id == "dsomm" and .state == "RUNNING")' <<<"$apps_json" >/dev/null; then
  run_gate dsomm python3 "${ROOT}/scripts/truenas/check-dsomm-post-reboot.py"
else
  echo 'WARN DSOMM not RUNNING; skipping DSOMM check'
  warnings=$((warnings + 1))
fi

if [[ -f "${ROOT}/scripts/truenas/diagnose-fastapi-integrations.py" ]]; then
  run_gate fastapi-integrations python3 "${ROOT}/scripts/truenas/diagnose-fastapi-integrations.py"
else
  echo 'WARN FastAPI diagnostic unavailable'
  warnings=$((warnings + 1))
fi

if [[ -f "${ROOT}/scripts/ingress/audit-internal-routes.py" ]]; then
  run_gate ingress-routes python3 "${ROOT}/scripts/ingress/audit-internal-routes.py" --strict
else
  printf '%s⚠️ WARN ingress audit unavailable%s\n' "$YELLOW" "$RESET"
  warnings=$((warnings + 1))
fi

printf '\n📊 Homelab result: failures=%d warnings=%d\n' "$failed" "$warnings"
((failed == 0))
