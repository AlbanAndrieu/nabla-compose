#!/usr/bin/env bash
# Reconcile the repository-backed Gatus Custom App without resetting SQLite.
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
Usage: sudo bash scripts/truenas/deploy-gatus.sh [--check|--apply]

--check  Read-only source/runtime drift check.
--apply  Reconcile the TrueNAS Custom App from apps/gatus/compose.yml, repair
         only generated config access when needed, then accept HTTP health.

Existing /mnt/cpool/gatus/gatus.db is never deleted, replaced or chmod/chowned.
EOF
    exit 0
    ;;
  *)
    printf 'ERROR: unknown mode: %s\n' "${MODE}" >&2
    exit 2
    ;;
esac
(($# <= 1)) || {
  printf 'ERROR: unexpected arguments\n' >&2
  exit 2
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/truenas.sh
source "${ROOT}/scripts/lib/truenas.sh"

APP_ID="${GATUS_APP_ID:-gatus}"
SERVICE="${GATUS_SERVICE:-gatus}"
COMPOSE="${ROOT}/apps/gatus/compose.yml"
REPAIR="${ROOT}/scripts/truenas/repair-gatus-config-access.sh"
DIAGNOSE="${ROOT}/scripts/truenas/diagnose-gatus.sh"
URL="${GATUS_HEALTH_URL:-http://172.17.0.24:8085/health}"
DB="${GATUS_DB_PATH:-/mnt/cpool/gatus/gatus.db}"
WAIT_SECONDS="${GATUS_WAIT_SECONDS:-180}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command in curl docker git jq midclt stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "missing ${command}"
done

# Git index must never be refreshed as root: root git status rewrites .git/index.
if ((EUID == 0)); then
  command -v runuser >/dev/null 2>&1 || fail 'runuser is required for unprivileged Git metadata inspection'
  runuser -u albandrieu -- bash -c 'source "$1"; truenas_repo_provenance "$2"' \
    _ "${ROOT}/scripts/lib/truenas.sh" "${ROOT}"
  GIT_CMD=(runuser -u albandrieu -- git -C "${ROOT}")
else
  truenas_repo_provenance "${ROOT}"
  GIT_CMD=(git -C "${ROOT}")
fi

printf '==> Gatus source contract\n'
docker compose -f "${COMPOSE}" config --quiet ||
  fail 'Gatus Compose does not render'
grep -Fq 'group_add:' "${COMPOSE}" ||
  fail 'Gatus supplemental group contract is missing'
grep -Fq './config:/config:ro' "${COMPOSE}" ||
  fail 'Gatus read-only config mount is missing'
grep -Fq '/mnt/cpool/gatus:/data' "${COMPOSE}" ||
  fail 'Gatus persistent data mount is missing'

printf '\n==> Gatus scoped Git cleanliness\n'
if "${GIT_CMD[@]}" diff --quiet -- apps/gatus scripts/truenas/deploy-gatus.sh scripts/truenas/repair-gatus-config-access.sh scripts/truenas/diagnose-gatus.sh &&
  "${GIT_CMD[@]}" diff --cached --quiet -- apps/gatus scripts/truenas/deploy-gatus.sh scripts/truenas/repair-gatus-config-access.sh scripts/truenas/diagnose-gatus.sh; then
  printf 'OK: Gatus deployment scope is clean\n'
else
  fail 'Gatus deployment scope is dirty; commit or restore this scope before apply'
fi

db_identity_before=''
if [[ -e "${DB}" ]]; then
  db_identity_before="$(stat -c '%d:%i' -- "${DB}")"
  printf 'gatus_db=present identity=%s metadata-preserved\n' "${db_identity_before}"
else
  printf 'gatus_db=absent before reconciliation\n'
fi

printf '\n==> Current Gatus runtime\n'
printf 'gatus_app_state=%s\n' "$(truenas_app_state "${APP_ID}")"
container_id="$(truenas_compose_container_id "${APP_ID}" "${SERVICE}")"
if [[ -n "${container_id}" ]]; then
  docker inspect "${container_id}"     --format 'gatus_container={{.Id}} status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}}'
fi

if [[ "${MODE}" == '--check' ]]; then
  "${DIAGNOSE}"
  "${REPAIR}" --check
  curl -fsS --connect-timeout 3 --max-time 8 -o /dev/null "${URL}" ||
    fail "Gatus HTTP health failed: ${URL}"
  printf 'OK: Gatus source, config access and HTTP health are accepted\n'
  exit 0
fi

((EUID == 0)) || fail '--apply requires root on TrueNAS'

printf '\n==> Reconcile only the Gatus TrueNAS Custom App\n'
lifecycle_mark="$(truenas_lifecycle_mark)"
truenas_reconcile_custom_app "${APP_ID}" "${COMPOSE}"
# app.update may succeed without recreating an existing restarting container.
# The explicit --apply transaction must reinstantiate the app to receive GroupAdd.
truenas_job_compact app.redeploy "${APP_ID}"
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 3
truenas_lifecycle_errors_since "${APP_ID}" "${lifecycle_mark}" 30 || true

printf '\n==> Repair generated config access only when required\n'
if ! "${REPAIR}" --check; then
  "${REPAIR}" --apply
fi
"${REPAIR}" --check

printf '\n==> Wait for stable Gatus process and HTTP health\n'
deadline=$((SECONDS + WAIT_SECONDS))
while ((SECONDS < deadline)); do
  container_id="$(truenas_compose_container_id "${APP_ID}" "${SERVICE}")"
  if [[ -n "${container_id}" ]]; then
    runtime_status="$(docker inspect "${container_id}" --format '{{.State.Status}}' 2>/dev/null || true)"
    restart_count="$(docker inspect "${container_id}" --format '{{.RestartCount}}' 2>/dev/null || true)"
    if [[ "${runtime_status}" == running ]] &&
      curl -fsS --connect-timeout 3 --max-time 8 -o /dev/null "${URL}" 2>/dev/null; then
      printf 'OK: Gatus running HTTP healthy restarts=%s\n' "${restart_count:-unknown}"
      break
    fi
  fi
  sleep 3
done
curl -fsS --connect-timeout 3 --max-time 8 -o /dev/null "${URL}" ||
  fail "Gatus did not become HTTP healthy within ${WAIT_SECONDS}s"

if [[ -n "${db_identity_before}" ]]; then
  [[ -e "${DB}" ]] || fail 'existing Gatus SQLite database disappeared'
  db_identity_after="$(stat -c '%d:%i' -- "${DB}")"
  [[ "${db_identity_after}" == "${db_identity_before}" ]] ||
    fail 'existing Gatus SQLite database inode changed; stop and investigate'
  printf 'OK: existing Gatus SQLite inode preserved\n'
fi

printf 'OK: Gatus Custom App reconciliation accepted without SQLite reset\n'
