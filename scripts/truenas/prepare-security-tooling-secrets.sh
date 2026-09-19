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
warn() {
  printf 'WARNING: %s\n' "$*" >&2
}

case "${MODE}" in
  --check | --apply | --verify-vaultwarden | --import-env | --import-env-apply) ;;
  *) fail "usage: $0 [--check|--apply|--verify-vaultwarden|--import-env|--import-env-apply] [app|all]" ;;
esac
[[ -n "${ROOT}" ]] || fail "run from repository checkout"

if [[ "${TARGET}" != "all" ]]; then
  found=0
  for app in "${APPS[@]}"; do
    [[ "${app}" == "${TARGET}" ]] && found=1
  done
  ((found == 1)) || fail "unsupported app: ${TARGET}"
  APPS=("${TARGET}")
fi

python3 scripts/secrets/render_from_bitwarden.py --check

if [[ "${MODE}" == "--import-env" || "${MODE}" == "--import-env-apply" ]]; then
  args=()
  for app in "${APPS[@]}"; do
    args+=(--app "${app}")
  done
  if [[ "${MODE}" == "--import-env-apply" ]]; then
    [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION required for --import-env-apply"
    command -v bw >/dev/null 2>&1 || fail "bw CLI required for --import-env-apply"
    python3 scripts/secrets/import_env_to_bitwarden.py "${args[@]}" --apply
  else
    python3 scripts/secrets/import_env_to_bitwarden.py "${args[@]}"
  fi
  exit 0
fi

verify_one() {
  local app="$1"
  local target="/mnt/cpool/secrets/runtime/${app}/.env.secrets"
  local tmp

  case "${MODE}" in
    --apply)
      [[ "${EUID}" -eq 0 ]] || fail "--apply requires sudo -E"
      [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION required for --apply"
      command -v bw >/dev/null 2>&1 || fail "bw CLI required for --apply"
      install -d -o root -g root -m 700 "$(dirname "${target}")"
      python3 scripts/secrets/render_from_bitwarden.py         --app "${app}"         --output-file "${target}"
      chown root:root "${target}"
      chmod 600 "${target}"
      ;;
    --verify-vaultwarden)
      [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION required for --verify-vaultwarden"
      command -v bw >/dev/null 2>&1 || fail "bw CLI required for --verify-vaultwarden"
      [[ -f "${target}" ]] || fail "missing runtime materialization: ${target}"
      tmp="$(mktemp)"
      trap 'rm -f "${tmp}"' RETURN
      python3 scripts/secrets/render_from_bitwarden.py         --app "${app}"         --output-file "${tmp}" >/dev/null
      cmp -s "${tmp}" "${target}" ||
        fail "${app}: Vaultwarden render differs from runtime materialization"
      rm -f "${tmp}"
      trap - RETURN
      ;;
    --check)
      [[ -f "${target}" ]] || fail "missing runtime materialization: ${target}"
      [[ -s "${target}" ]] || fail "empty runtime materialization: ${target}"
      metadata="$(stat -c '%U:%G %a' "${target}")"
      [[ "${metadata}" == "root:root 600" ]] ||
        fail "${app}: ${target} owner/mode=${metadata}; expected root:root 600"
      ;;
  esac

  printf 'OK: secret contract app=%s mode=%s\n' "${app}" "${MODE}"
}

for app in "${APPS[@]}"; do
  verify_one "${app}"
done

if [[ "${MODE}" == "--check" && -n "${BW_SESSION:-}" && -x "$(command -v bw 2>/dev/null || true)" ]]; then
  warn "runtime files are valid; run --verify-vaultwarden to prove byte-for-byte parity with the unlocked vault"
fi
