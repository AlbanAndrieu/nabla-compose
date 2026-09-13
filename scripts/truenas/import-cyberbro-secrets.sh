#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
UPDATE_EXISTING="${CYBERBRO_UPDATE_EXISTING:-0}"
CANONICAL_ROOT="${CYBERBRO_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply] (set CYBERBRO_UPDATE_EXISTING=1 to update an existing Vaultwarden item)" ;;
esac

for command in git python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

args=(--app cyberbro)
if [[ "${MODE}" == "--apply" ]]; then
  [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION is required for --apply; unlock Bitwarden first and preserve it with sudo -E if needed"
  command -v bw >/dev/null 2>&1 || fail "bw is required for --apply"
  args+=(--apply)
  if [[ "${UPDATE_EXISTING}" == "1" ]]; then
    args+=(--update-existing)
  fi
fi

python3 scripts/secrets/import_env_to_bitwarden.py "${args[@]}"

if [[ "${MODE}" == "--apply" ]]; then
  printf 'OK: Cyberbro provider values imported to Vaultwarden metadata contract.\n'
  printf 'INFO: materialize the canonical runtime file with: sudo -E bash scripts/truenas/bootstrap-cyberbro-env.sh --apply\n'
else
  printf 'OK: Cyberbro Vaultwarden import dry-run completed.\n'
fi
