#!/usr/bin/env bash
# Compatibility wrapper: the shared implementation is bootstrap-app-postgres.sh.
#   sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh [--check|--apply]
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The historical SCANOPY_SECRETS_FILE override keeps working.
export NABLA_APP_SECRETS_FILE="${SCANOPY_SECRETS_FILE:-${NABLA_APP_SECRETS_FILE:-}}"
[[ -n "${NABLA_APP_SECRETS_FILE}" ]] || unset NABLA_APP_SECRETS_FILE
exec bash "${SCRIPT_DIR}/bootstrap-app-postgres.sh" "${1:---check}" scanopy
