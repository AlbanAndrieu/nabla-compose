#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP="${2:-}"
LEGACY_PATH="${3:-}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
MANIFEST="${NABLA_SECRETS_MANIFEST:-config/secrets/manifest.json}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
usage: scripts/secrets/reconcile_service_secrets.sh MODE APP [legacy-path]

Modes:
  --check                verify installed root-only runtime materialization
  --import-env           dry-run import from current operator environment
  --import-env-apply     create/update Vaultwarden from current environment
  --import-legacy        dry-run import from a root-readable historical dotenv
  --import-legacy-apply  create/update Vaultwarden from the historical dotenv
  --install              render from Vaultwarden as operator, install as root
  --verify               render from Vaultwarden and compare with installed file

Vaultwarden access always runs as the unprivileged operator. BW_SESSION is
explicitly removed from every sudo/root subprocess.
EOF
}

[[ -n "${MODE}" && -n "${APP}" ]] || { usage >&2; exit 2; }
[[ -n "${ROOT}" ]] || fail "run from the repository checkout"
cd "${ROOT}"

python3 scripts/secrets/render_from_bitwarden.py --manifest "${MANIFEST}" --check >/dev/null

readarray -t meta < <(
  python3 - "${MANIFEST}" "${APP}" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
app = sys.argv[2]
matches = [item for item in manifest["items"] if item.get("app") == app]
if len(matches) != 1:
    raise SystemExit(f"expected one manifest item for {app!r}, found {len(matches)}")
item = matches[0]
print(item.get("service") or app)
print(item.get("runtimeFile") or ".env.secrets")
PY
)
SERVICE="${meta[0]}"
RUNTIME_FILE="${meta[1]}"

case "${MODE}" in
  --import-env)
    exec python3 scripts/secrets/import_env_to_bitwarden.py       --manifest "${MANIFEST}" --app "${APP}"
    ;;
  --import-env-apply)
    [[ "${EUID}" -ne 0 ]] || fail "Vaultwarden writes must run as the unprivileged operator"
    [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION is required"
    exec python3 scripts/secrets/import_env_to_bitwarden.py       --manifest "${MANIFEST}" --app "${APP}" --apply
    ;;
  --import-legacy | --import-legacy-apply)
    [[ -n "${LEGACY_PATH}" ]] || fail "legacy path required"
    [[ "${EUID}" -ne 0 ]] || fail "Vaultwarden writes/reads must run as the unprivileged operator"
    [[ -n "${BW_SESSION:-}" || "${MODE}" == "--import-legacy" ]] ||
      fail "BW_SESSION is required for --import-legacy-apply"
    args=(--manifest "${MANIFEST}" --app "${APP}" --dotenv-file -)
    [[ "${MODE}" == "--import-legacy-apply" ]] && args+=(--apply)
    sudo env -u BW_SESSION cat -- "${LEGACY_PATH}" |
      python3 scripts/secrets/import_env_to_bitwarden.py "${args[@]}"
    ;;
  --check)
    exec sudo env -u BW_SESSION       NABLA_RUNTIME_SECRET_FILE="${RUNTIME_FILE}"       bash scripts/truenas/install-runtime-secret.sh --check "${SERVICE}"
    ;;
  --install | --verify)
    [[ "${EUID}" -ne 0 ]] || fail "Vaultwarden rendering must run as the unprivileged operator"
    [[ -n "${BW_SESSION:-}" ]] || fail "BW_SESSION is required"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "${tmpdir}"' EXIT
    candidate="${tmpdir}/${RUNTIME_FILE}"
    python3 scripts/secrets/render_from_bitwarden.py       --manifest "${MANIFEST}"       --app "${APP}"       --output-file "${candidate}" >/dev/null
    root_mode="--apply"
    [[ "${MODE}" == "--verify" ]] && root_mode="--compare"
    sudo env -u BW_SESSION       NABLA_RUNTIME_SECRET_FILE="${RUNTIME_FILE}"       bash scripts/truenas/install-runtime-secret.sh       "${root_mode}" "${SERVICE}" "${candidate}"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
