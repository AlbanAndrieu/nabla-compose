#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TARGET="${2:-all}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
APPS=(plumber netbox dependency-track defectdojo neo4j cartography scorecard)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply | --verify-vaultwarden | --import-env | --import-env-apply) ;;
  *) fail "usage: $0 [--check|--apply|--verify-vaultwarden|--import-env|--import-env-apply] [app|all]" ;;
esac
[[ -n "${ROOT}" ]] || fail "run from repository checkout"
cd "${ROOT}"

if [[ "${TARGET}" != "all" ]]; then
  found=0
  for app in "${APPS[@]}"; do
    [[ "${app}" == "${TARGET}" ]] && found=1
  done
  ((found == 1)) || fail "unsupported security tooling app: ${TARGET}"
  APPS=("${TARGET}")
fi

case "${MODE}" in
  --check) generic_mode="--check" ;;
  --apply) generic_mode="--install" ;;
  --verify-vaultwarden) generic_mode="--verify" ;;
  --import-env) generic_mode="--import-env" ;;
  --import-env-apply) generic_mode="--import-env-apply" ;;
esac

if [[ "${generic_mode}" == "--install" || "${generic_mode}" == "--verify" || "${generic_mode}" == "--import-env-apply" ]]; then
  [[ "${EUID}" -ne 0 ]] ||
    fail "${MODE} must run as the unprivileged Vaultwarden operator; the generic reconciler invokes sudo only for the final root-owned file operation"
fi

for app in "${APPS[@]}"; do
  bash scripts/secrets/reconcile_service_secrets.sh "${generic_mode}" "${app}"
done
