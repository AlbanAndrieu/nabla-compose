#!/usr/bin/env bash
# Controlled TrueNAS Scanopy Custom App deployment on the shared PostgreSQL.
#   sudo bash scripts/truenas/deploy-scanopy.sh --check    # read-only preflight (default)
#   sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/deploy-scanopy.sh --apply
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/app-deploy.sh
source "${SCRIPT_DIR}/../lib/app-deploy.sh"

MODE="$(app_deploy_mode "${1:-}" "$0")" || exit 2
APP_ID="${SCANOPY_APP_ID:-scanopy}"
CANONICAL_ROOT="${SCANOPY_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRETS_FILE="${SCANOPY_SECRETS_FILE:-/mnt/cpool/secrets/runtime/scanopy/.env.secrets}"
compose_path="${CANONICAL_ROOT}/apps/scanopy/compose.yml"

app_deploy_canonical_checkout "${CANONICAL_ROOT}"

[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"
# Check the immutable image contract before preparing any TrueNAS runtime state.
bash "${SCRIPT_DIR}/check-scanopy-image-lock.sh" "${compose_path}"

if [[ "${MODE}" == "--apply" ]]; then
  [[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
    fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check preflight"
  bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
fi
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

secrets_assert_file "${SECRETS_FILE}" POSTGRES_PASSWORD SCANOPY_DATABASE_URL ||
  fail "Scanopy secret contract is not satisfied (root:root mode 0600 with POSTGRES_PASSWORD and SCANOPY_DATABASE_URL)"
bash scripts/truenas/bootstrap-scanopy-postgres.sh --check ||
  fail "shared PostgreSQL role/database scanopy is not ready; run: sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --apply"
ok "shared PostgreSQL dependency verified: 172.17.0.24:5432 role/database=scanopy"

app_deploy_compose_validate "${compose_path}"

if [[ "${MODE}" == "--check" ]]; then
  app_deploy_check_report "${APP_ID}"
  exit 0
fi
app_deploy_reconcile "${APP_ID}" "${compose_path}"
