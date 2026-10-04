#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

MODE="${1:---check}"
APP_ID="${SENTRY_APP_ID:-sentry}"
WAIT_SECONDS="${SENTRY_RECOVERY_WAIT_SECONDS:-1200}"

usage() {
  cat <<'EOF'
usage: sudo bash scripts/truenas/recover-sentry-deploying.sh [--check|--apply]

--check is read-only and validates the two known secret prerequisites plus the
current Sentry diagnostic.
--apply repairs only missing bounded credential material, redeploys only the
Sentry TrueNAS App, waits for RUNNING, then requires diagnostic + E2E ingestion
success. It never resets Kafka offsets, deletes topics/databases, or restarts
shared Kafka/Redis/PostgreSQL/ClickHouse Apps.
EOF
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands bash midclt jq docker curl

system_secret="${SCRIPT_DIR}/reconcile-sentry-system-secret.sh"
migrator_secret="${SCRIPT_DIR}/reconcile-sentry-migrator-credential.sh"
diagnostic="${SCRIPT_DIR}/diagnose-sentry.sh"
smoke="${SCRIPT_DIR}/smoke-sentry-event.sh"

for helper in "${system_secret}" "${migrator_secret}" "${diagnostic}" "${smoke}"; do
  [[ -f "${helper}" ]] || fail "missing Sentry helper: ${helper}"
done

printf '==> Sentry runtime credential preflight\n'
if [[ "${MODE}" == "--apply" ]]; then
  if ! bash "${system_secret}" --check; then
    bash "${system_secret}" --apply
  fi
  if ! bash "${migrator_secret}" --check; then
    bash "${migrator_secret}" --apply
  fi
else
  bash "${system_secret}" --check
  bash "${migrator_secret}" --check
fi

if [[ "${MODE}" == "--check" ]]; then
  printf '\n==> current Sentry lifecycle diagnosis\n'
  exec bash "${diagnostic}" --check
fi

printf '\n==> targeted Sentry redeploy\n'
state="$(truenas_app_state "${APP_ID}")"
[[ "${state}" != "MISSING" ]] || fail "TrueNAS App is missing: ${APP_ID}"
printf 'Sentry state before redeploy: %s\n' "${state}"
midclt call -j app.redeploy "${APP_ID}"

printf '\n==> wait for TrueNAS RUNNING\n'
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 5

printf '\n==> Sentry functional diagnosis\n'
bash "${diagnostic}" --check

printf '\n==> Sentry end-to-end ingestion smoke\n'
bash "${smoke}"

printf '\n==> canonical runtime-secret staging\n'
bash "${SCRIPT_DIR}/bootstrap-repository-env-files.sh" --restage sentry

ok "Sentry redeploy converged; canonical runtime secret copies refreshed"
printf 'NEXT: after the observation window, finalize only Sentry legacy env paths:\n'
printf '  sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize sentry\n'
