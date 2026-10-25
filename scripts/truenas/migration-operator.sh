#!/usr/bin/env bash
# Stable operator entrypoint: delegates to the reviewed legacy migration CLI.
# No default remediation; no sourced global shell state.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUNNER="${SCRIPT_DIR}/finish-migrations-20261024.sh"
if [[ ! -f "${RUNNER}" || -L "${RUNNER}" ]]; then
  printf '%s\n' 'BLOCKED: canonical migration operator unavailable or symlinked' >&2
  exit 2
fi

# Exec inside a child shell, preserving the caller's interactive options.
exec bash "${RUNNER}" "$@"
