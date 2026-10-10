#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
Usage: sudo bash scripts/truenas/deploy-crowdsec.sh [--check|--apply]

--check  Read-only source/runtime readiness check. Missing cutover credentials
         are warnings, not blockers for central-engine reconciliation.
--apply  Reconcile only the TrueNAS CrowdSec Custom App, wait for RUNNING,
         then rerun the read-only --runtime diagnostic.

The helper never changes pfSense, never creates/deletes a bouncer, never
rotates a key and never starts the pfSense CrowdSec Security Engine.
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

APP_ID="crowdsec"
COMPOSE="${ROOT}/apps/crowdsec/compose.yml"
DIAGNOSE="${ROOT}/scripts/truenas/diagnose-crowdsec-cutover.sh"
SECRET_FILE="${CROWDSEC_SECRET_FILE:-/mnt/cpool/secrets/runtime/crowdsec/.env.secrets}"
WAIT_SECONDS="${CROWDSEC_APP_WAIT_SECONDS:-600}"

errors=0
warnings=0
ok() { printf 'OK: %s\n' "$*"; }
warn_check() { printf 'WARNING: %s\n' "$*" >&2; warnings=$((warnings + 1)); }
fail_check() { printf 'ERROR: %s\n' "$*" >&2; errors=$((errors + 1)); }

for command in docker git grep jq midclt stat; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: required command missing: %s\n' "${command}" >&2
    exit 2
  }
done

truenas_repo_provenance "${ROOT}"

printf '==> CrowdSec source contract\n'
if grep -q 'image: crowdsecurity/crowdsec:v1.8.1' "${COMPOSE}"; then
  ok 'CrowdSec image is pinned to v1.8.1'
else
  fail_check 'CrowdSec image pin is not v1.8.1'
fi
if grep -q 'DISABLE_SCENARIOS: firewallservices/pf-scan-multi_ports' "${COMPOSE}"; then
  ok 'problematic pf-scan-multi_ports scenario is disabled in source'
else
  fail_check 'pf-scan-multi_ports exclusion is missing from source'
fi
if grep -q 'source: loki' "${ROOT}/apps/crowdsec/acquis.d/security.yaml" &&
  grep -q 'job="pfsense", device="pfsense"' "${ROOT}/apps/crowdsec/acquis.d/security.yaml"; then
  ok 'pfSense acquisition uses the canonical Loki stream'
else
  fail_check 'pfSense Loki acquisition contract is missing'
fi
if docker compose -f "${COMPOSE}" config --quiet >/dev/null 2>&1; then
  ok 'CrowdSec Compose renders successfully'
else
  fail_check 'CrowdSec Compose render failed'
fi

printf '\n==> CrowdSec cutover credential contract\n'
if [[ ! -s "${SECRET_FILE}" ]]; then
  warn_check "canonical CrowdSec runtime file missing or empty; central runtime can be reconciled, pfSense cutover remains blocked: ${SECRET_FILE}"
else
  secret_metadata="$(stat -c '%U:%G %a' "${SECRET_FILE}" 2>/dev/null || true)"
  printf 'crowdsec_secret_file=%s metadata=%s\n' "${SECRET_FILE}" "${secret_metadata:-unknown}"
  [[ "${secret_metadata}" == 'root:root 600' ]] ||
    fail_check 'existing CrowdSec runtime file must be root:root 0600'
  if grep -Eq '^BOUNCER_KEY_PFSENSE_FIREWALL=.+$' "${SECRET_FILE}"; then
    ok 'pfSense bouncer credential is present (value redacted)'
  else
    warn_check 'BOUNCER_KEY_PFSENSE_FIREWALL is missing or empty; pfSense cutover remains blocked'
  fi
fi

printf '\n==> CrowdSec scoped Git cleanliness\n'
if git -C "${ROOT}" diff --quiet -- apps/crowdsec scripts/truenas/deploy-crowdsec.sh scripts/truenas/diagnose-crowdsec-cutover.sh &&
  git -C "${ROOT}" diff --cached --quiet -- apps/crowdsec scripts/truenas/deploy-crowdsec.sh scripts/truenas/diagnose-crowdsec-cutover.sh; then
  ok 'CrowdSec deployment scope is clean'
else
  fail_check 'CrowdSec deployment scope is dirty; commit/stash only this scope before apply'
fi

printf '\n==> Current TrueNAS CrowdSec runtime\n'
current_state="$(truenas_app_state "${APP_ID}")"
current_container="$(truenas_compose_container_id "${APP_ID}" crowdsec)"
printf 'crowdsec_app_state=%s\n' "${current_state}"
if [[ -n "${current_container}" ]]; then
  current_image="$(docker inspect "${current_container}" --format '{{.Config.Image}}' 2>/dev/null || true)"
  current_health="$(docker inspect "${current_container}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || true)"
  printf 'crowdsec_container_id=%s image=%s health=%s\n' \
    "${current_container:0:12}" "${current_image:-unknown}" "${current_health:-unknown}"
else
  printf 'crowdsec_container_id=<none> image=<none> health=<none>\n'
fi

if [[ "${MODE}" == '--check' ]]; then
  if ! "${DIAGNOSE}" --runtime; then
    fail_check 'CrowdSec central runtime diagnostic is not ready'
  fi
  ((errors == 0))
  exit
fi

((EUID == 0)) || {
  printf 'ERROR: --apply requires root on TrueNAS\n' >&2
  exit 2
}
if ((errors > 0)); then
  printf 'ERROR: refusing CrowdSec apply with %s failed precondition(s)\n' "${errors}" >&2
  exit 1
fi

printf '\n==> Reconcile only the CrowdSec TrueNAS Custom App\n'
lifecycle_mark="$(truenas_lifecycle_mark)"
truenas_reconcile_custom_app "${APP_ID}" "${COMPOSE}"
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 4
truenas_lifecycle_errors_since "${APP_ID}" "${lifecycle_mark}" 40

printf '\n==> Post-reconcile CrowdSec validation\n'
"${DIAGNOSE}" --runtime
printf 'OK: CrowdSec TrueNAS runtime reconciliation completed; pfSense was not modified\n'
if ((warnings > 0)); then
  printf 'WARNING: CrowdSec runtime is reconciled but %s cutover prerequisite warning(s) remain\n' "${warnings}" >&2
fi
