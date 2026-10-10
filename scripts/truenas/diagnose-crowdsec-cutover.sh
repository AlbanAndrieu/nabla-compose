#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --check | --accept) ;;
  -h | --help)
    cat <<'EOF'
Usage: sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh [--check|--accept]

Read-only validation for the CrowdSec Security Engine/LAPI migration to TrueNAS.
--check   Pre-cutover readiness. A registered pfSense bouncer is required; a
          missing last_pull is reported as a warning because pfSense may not
          have switched to the remote LAPI yet.
--accept  Post-cutover acceptance. Requires the pfSense bouncer to have polled
          the central LAPI at least once.

No service restart, app redeploy, bouncer creation, key rotation or pfSense
mutation is performed.
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

APP_ID="${CROWDSEC_APP_ID:-crowdsec}"
SERVICE="${CROWDSEC_SERVICE:-crowdsec}"
EXPECTED_IMAGE="${CROWDSEC_EXPECTED_IMAGE:-crowdsecurity/crowdsec:v1.8.1}"
SECRET_FILE="${CROWDSEC_SECRET_FILE:-/mnt/cpool/crowdsec/.env.secrets}"
PFSENSE_LOG_DIR="${PFSENSE_LOG_DIR:-/mnt/cpool/logs/pfsense}"
LAPI_HOST="${CROWDSEC_LAPI_BIND_ADDRESS:-172.17.0.24}"
LAPI_PORT="${CROWDSEC_LAPI_PORT:-8084}"
METRICS_HOST="${CROWDSEC_METRICS_BIND_ADDRESS:-172.17.0.24}"
METRICS_PORT="${CROWDSEC_METRICS_PORT:-6060}"
DISABLED_SCENARIO="firewallservices/pf-scan-multi_ports"
BOUNCER_NAME="PFSENSE_FIREWALL"

failures=0
warnings=0

ok() { printf 'OK: %s\n' "$*"; }
warn() { warnings=$((warnings + 1)); printf 'WARNING: %s\n' "$*" >&2; }
error() { failures=$((failures + 1)); printf 'ERROR: %s\n' "$*" >&2; }

for command in docker jq midclt ss stat find grep timeout sed awk tail; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: required command missing: %s\n' "${command}" >&2
    exit 2
  }
done

truenas_repo_provenance "${ROOT}"

printf '==> TrueNAS CrowdSec app\n'
app_state="$(truenas_app_state "${APP_ID}")"
printf 'crowdsec_app_state=%s\n' "${app_state}"
[[ "${app_state}" == "RUNNING" ]] || error "TrueNAS App ${APP_ID} must be RUNNING before cutover"

container_id="$(truenas_compose_container_id "${APP_ID}" "${SERVICE}")"
if [[ -z "${container_id}" ]]; then
  error "CrowdSec Compose container is missing"
else
  runtime_status="$(docker inspect "${container_id}" --format '{{.State.Status}}' 2>/dev/null || true)"
  runtime_health="$(docker inspect "${container_id}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || true)"
  runtime_image="$(docker inspect "${container_id}" --format '{{.Config.Image}}' 2>/dev/null || true)"
  printf 'crowdsec_container_id=%s status=%s health=%s image=%s\n' \
    "${container_id:0:12}" "${runtime_status:-unknown}" "${runtime_health:-unknown}" "${runtime_image:-unknown}"
  [[ "${runtime_status}" == "running" ]] || error "CrowdSec container is not running"
  [[ "${runtime_image}" == "${EXPECTED_IMAGE}" ]] || error "CrowdSec runtime image is ${runtime_image:-unknown}; expected ${EXPECTED_IMAGE}"

  disabled_scenarios="$(docker inspect "${container_id}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^DISABLE_SCENARIOS=//p' | tail -n 1)"
  case " ${disabled_scenarios} " in
    *" ${DISABLED_SCENARIO} "*) ok "problematic scenario disabled in runtime environment: ${DISABLED_SCENARIO}" ;;
    *) error "runtime does not disable ${DISABLED_SCENARIO}" ;;
  esac

  if timeout 12 docker exec "${container_id}" cscli lapi status >/dev/null 2>&1; then
    ok "central CrowdSec LAPI responds inside the container"
  else
    error "central CrowdSec LAPI status failed"
  fi

  if timeout 12 docker exec "${container_id}" sh -c 'test ! -e /etc/crowdsec/scenarios/pf-scan-multi_ports.yaml'; then
    ok "pf-scan-multi_ports scenario file is absent after container bootstrap"
  else
    error "pf-scan-multi_ports scenario is still installed in the central engine"
  fi
fi

printf '\n==> LAN-only listeners\n'
if ss -ltnH | awk -v endpoint="${LAPI_HOST}:${LAPI_PORT}" '$4 == endpoint {found=1} END {exit !found}'; then
  ok "LAPI listener is bound to ${LAPI_HOST}:${LAPI_PORT}"
else
  error "expected LAPI listener missing on ${LAPI_HOST}:${LAPI_PORT}"
fi
if ss -ltnH | awk -v endpoint="${METRICS_HOST}:${METRICS_PORT}" '$4 == endpoint {found=1} END {exit !found}'; then
  ok "metrics listener is bound to ${METRICS_HOST}:${METRICS_PORT}"
else
  warn "expected CrowdSec metrics listener missing on ${METRICS_HOST}:${METRICS_PORT}"
fi

printf '\n==> Secret and log-source readiness\n'
if [[ ! -r "${SECRET_FILE}" ]]; then
  error "pfSense bouncer secret file is missing or unreadable: ${SECRET_FILE}"
else
  secret_mode="$(stat -c '%a' "${SECRET_FILE}" 2>/dev/null || true)"
  printf 'crowdsec_secret_file=%s mode=%s\n' "${SECRET_FILE}" "${secret_mode:-unknown}"
  [[ "${secret_mode}" == "600" ]] || error "CrowdSec secret file must be mode 0600"
  if grep -Eq '^BOUNCER_KEY_PFSENSE_FIREWALL=.+$' "${SECRET_FILE}"; then
    ok "pfSense bouncer credential is present (value redacted)"
  else
    error "BOUNCER_KEY_PFSENSE_FIREWALL is missing or empty"
  fi
fi

if [[ ! -d "${PFSENSE_LOG_DIR}" ]]; then
  error "pfSense log directory is missing: ${PFSENSE_LOG_DIR}"
else
  pfsense_log="$(find "${PFSENSE_LOG_DIR}" -maxdepth 1 -type f -name '*.log' -print -quit 2>/dev/null || true)"
  if [[ -n "${pfsense_log}" ]]; then
    ok "pfSense log acquisition source exists"
  else
    error "no pfSense *.log acquisition source found in ${PFSENSE_LOG_DIR}"
  fi
fi

printf '\n==> Central LAPI bouncer registration\n'
if [[ -n "${container_id:-}" ]]; then
  bouncer_json="$(timeout 12 docker exec "${container_id}" cscli bouncers list -o json 2>/dev/null || true)"
  bouncer_count="$(jq --arg name "${BOUNCER_NAME}" '[.[]? | select(.name == $name)] | length' <<<"${bouncer_json:-[]}" 2>/dev/null || printf '0')"
  if [[ "${bouncer_count}" == "1" ]]; then
    bouncer_status="$(jq -r --arg name "${BOUNCER_NAME}" '.[] | select(.name == $name) | "name=\(.name) ip=\(.ip_address // "<none>") last_pull=\(.last_pull // "<none>")"' <<<"${bouncer_json}")"
    printf 'crowdsec_bouncer_%s\n' "${bouncer_status}"
    last_pull="$(jq -r --arg name "${BOUNCER_NAME}" '.[] | select(.name == $name) | (.last_pull // "")' <<<"${bouncer_json}")"
    if [[ -n "${last_pull}" ]]; then
      ok "pfSense firewall bouncer has polled the central LAPI"
    elif [[ "${MODE}" == "--accept" ]]; then
      error "pfSense firewall bouncer is registered but has not polled the central LAPI"
    else
      warn "pfSense firewall bouncer is registered but has not polled yet; expected before cutover"
    fi
  else
    error "expected exactly one ${BOUNCER_NAME} bouncer registration, found ${bouncer_count}"
  fi
fi

printf '\nCrowdSec cutover summary: failures=%s warnings=%s mode=%s\n' "${failures}" "${warnings}" "${MODE}"
((failures == 0))
