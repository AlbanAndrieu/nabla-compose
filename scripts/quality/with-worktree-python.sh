#!/usr/bin/env bash
# Worktree-scoped locked Python dependencies, without direnv or system installs.
set -Eeuo pipefail
umask 077
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if (($# == 0)); then
  printf 'Usage: bash scripts/quality/with-worktree-python.sh [--setup-only|COMMAND [args...]]\n' >&2
  exit 2
fi
for file in pyproject.toml uv.lock; do
  [[ -f "$root/$file" ]] || { printf 'BLOCKED: missing %s in %s\n' "$file" "$root" >&2; exit 3; }
done
if [[ -L "$root/.venv" || ( -e "$root/.venv" && ! -d "$root/.venv" ) ]]; then
  printf 'BLOCKED: .venv is a symlink or not a directory\n' >&2
  exit 3
fi
for tool in python3 sha256sum flock; do
  command -v "$tool" >/dev/null 2>&1 || { printf 'BLOCKED: missing tool %s\n' "$tool" >&2; exit 3; }
done
uv_cmd="$(command -v uv || true)"
if [[ -z "$uv_cmd" ]] && command -v mise >/dev/null 2>&1; then
  mise_uv="$(mise where uv 2>/dev/null || true)"
  if [[ -x "$mise_uv/bin/uv" ]]; then uv_cmd="$mise_uv/bin/uv"; fi
fi
[[ -n "$uv_cmd" ]] || { printf 'BLOCKED: uv not installed; review mise.toml, then run mise install uv only\n' >&2; exit 3; }
venv="$root/.venv"
marker="$venv/.nabla-test-deps-sha256"
lock_sha="$(sha256sum "$root/pyproject.toml" "$root/uv.lock" | sha256sum | cut -d' ' -f1)"
lock_file="${TMPDIR:-/tmp}/nabla-worktree-python-$(printf '%s' "$root" | sha256sum | cut -c1-24).lock"
exec 9>"$lock_file"
flock -w 60 9 || { printf 'BLOCKED: local Python setup lock busy\n' >&2; exit 3; }
needs_sync=true
if [[ -x "$venv/bin/python" && -f "$marker" ]] &&
  [[ "$(cat "$marker")" == "$lock_sha" ]] &&
  "$venv/bin/python" -c 'import pytest, yaml' >/dev/null 2>&1; then
  needs_sync=false
fi
if [[ "$needs_sync" == true ]]; then
  printf 'INFO: syncing locked test dependencies into worktree .venv\n'
  (cd -- "$root" && UV_PYTHON_DOWNLOADS=never "$uv_cmd" sync --frozen --only-group test --no-install-project --python "$(command -v python3)") || {
    printf 'BLOCKED: uv sync failed; no quality checks were run\n' >&2
    exit 3
  }
  [[ -x "$venv/bin/python" ]] || { printf 'BLOCKED: uv did not create .venv/bin/python\n' >&2; exit 3; }
  "$venv/bin/python" -c 'import pytest, yaml' || { printf 'BLOCKED: pytest/PyYAML missing after locked sync\n' >&2; exit 3; }
  printf '%s\n' "$lock_sha" >"$marker"
fi
flock -u 9
export VIRTUAL_ENV="$venv"
export NABLA_TRUENAS_DEV_VENV="$venv"
export PATH="$venv/bin:$PATH"
if [[ "$1" == '--setup-only' ]]; then
  (($# == 1)) || exit 2
  printf 'PASS: worktree Python dependencies ready (%s)\n' "$venv"
  exit 0
fi
cd -- "$root"
exec "$@"
