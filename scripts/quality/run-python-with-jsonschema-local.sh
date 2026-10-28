#!/usr/bin/env bash
# Run an existing dependency-backed local Python. Never install packages or run CI.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if (($# == 0)); then
  printf '%s\n' 'usage: run-python-with-jsonschema-local.sh <script.py> [args...]' >&2
  exit 2
fi

candidates=()
if [[ -n "${NABLA_SECRETS_PYTHON:-}" ]]; then
  candidates+=("${NABLA_SECRETS_PYTHON}")
fi
candidates+=("${root}/.venv/bin/python" "python3" "/usr/bin/python3"
             "python3.13" "python3.12" "python3.11")

for candidate in "${candidates[@]}"; do
  if [[ "${candidate}" == */* ]]; then
    [[ -x "${candidate}" ]] || continue
    resolved="${candidate}"
  else
    resolved="$(command -v "${candidate}" 2>/dev/null)" || continue
  fi
  if "${resolved}" -c 'import jsonschema' >/dev/null 2>&1; then
    exec "${resolved}" "$@"
  fi
done

printf '%s\n' 'BLOCKED: no existing Python interpreter with jsonschema.' >&2
printf '%s\n' 'The key has NOT been checked in Vaultwarden; this is a local dependency issue.' >&2
printf '%s\n' 'ACTION: use the project-pinned test environment, without GitHub CI:' >&2
printf '%s\n' '  uv sync --group test --locked --offline  # only if dependencies are cached' >&2
printf '%s\n' '  just litellm-fastapi-upstream-source-check' >&2
printf '%s\n' 'Or set NABLA_SECRETS_PYTHON to an existing trusted venv Python.' >&2
exit 2
