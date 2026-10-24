# Launch repo Python dependency environment from any Git worktree.
# Invoked via bash, no shebang or executable bit required.
set -euo pipefail
if (($# == 0)); then
  printf 'usage: bash %s SCRIPT [args] | -m pytest [args]\n' "$0" >&2
  exit 2
fi
if [[ "${1:-}" == "-m" && "${2:-}" == pytest ]]; then
  REQUIRED_MODULES=(yaml pytest)
else
  REQUIRED_MODULES=(yaml)
fi
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
DEFAULT_VENV="${HOME}/.cache/nabla-compose/dev-venv"
CANDIDATES=(
  "${ROOT}/.venv/bin/python"
  "${NABLA_TRUENAS_DEV_VENV:-${DEFAULT_VENV}}/bin/python"
)
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  CANDIDATES+=("${VIRTUAL_ENV}/bin/python")
fi
CANDIDATES+=(python3 python)
for candidate in "${CANDIDATES[@]}"; do
  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || continue
  else
    command -v "$candidate" >/dev/null 2>&1 || continue
  fi
  if "$candidate" - "${REQUIRED_MODULES[@]}" <<'PY' >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if all(importlib.util.find_spec(item) for item in sys.argv[1:]) else 1)
PY
  then
    exec "$candidate" "$@"
  fi
done
# Bootstrap only in a linked worktree: avoid mutating the TrueNAS canonical checkout.
if [[ -f "${ROOT}/.git" && "${NABLA_WORKTREE_AUTO_SETUP:-1}" == 1 ]]; then
  exec bash "${ROOT}/scripts/quality/with-worktree-python.sh" "$@"
fi
printf 'BLOCKED: no Python with %s installed in existing repo environments.\n' \
  "${REQUIRED_MODULES[*]}" >&2
printf 'Development worktree only: initialize dependencies via your reviewed uv.lock/pyproject setup; no packages were installed.\n' >&2
exit 2
