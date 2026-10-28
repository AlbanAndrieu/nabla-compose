#!/usr/bin/env bash
# Local-only pytest runner. Never provisions packages or uses GitHub Actions.
# Prefer the invoking Python, then an existing project venv/system Python.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
candidates=()
if [[ -n "${NABLA_PYTEST_PYTHON:-}" ]]; then
  candidates+=("$NABLA_PYTEST_PYTHON")
fi
candidates+=("$root/.venv/bin/python" "python3" "/usr/bin/python3" "python3.13" "python3.12" "python3.11")

for candidate in "${candidates[@]}"; do
  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || continue
    resolved="$candidate"
  else
    resolved="$(command -v "$candidate" 2>/dev/null)" || continue
  fi
  # The import check never installs or modifies packages.
  if "$resolved" -c 'import pytest' >/dev/null 2>&1; then
    exec "$resolved" -m pytest "$@"
  fi
done

printf '%s\n' 'PYTEST_UNAVAILABLE: no existing Python interpreter with pytest was found.' >&2
printf '%s\n' 'ACTION: create a private local venv and install pytest (no GitHub CI):' >&2
printf '%s\n' '  python3 -m venv /tmp/nabla-pytest-venv' >&2
printf '%s\n' '  /tmp/nabla-pytest-venv/bin/python -m pip install pytest' >&2
printf '%s\n' '  NABLA_PYTEST_PYTHON=/tmp/nabla-pytest-venv/bin/python just <recipe>' >&2
printf '%s\n' 'No tests were executed; this is an environment dependency failure.' >&2
exit 2
