#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --runtime | --check | --accept) ;;
  -h | --help)
    cat <<'EOF'
Usage: sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh [--runtime|--check|--accept]

Read-only validation for the CrowdSec Security Engine/LAPI migration to TrueNAS.
--runtime Validate only the central TrueNAS runtime: image, scenario exclusion,
          LAPI/listeners and pfSense log acquisition through Loki.
--check   Pre-cutover readiness. Adds canonical credential and bouncer
          registration checks. A missing last_pull is only a warning.
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
SECRET_FILE="${CROWDSEC_SECRET_FILE:-/mnt/cpool/secrets/runtime/crowdsec/.env.secrets}"
LOKI_URL="${CROWDSEC_LOKI_URL:-http://172.17.0.24:3100}"
PFSENSE_LOG_LOOKBACK="${PFSENSE_LOG_LOOKBACK:-30m}"
LAPI_HOST="${CROWDSEC_LAPI_BIND_ADDRESS:-172.17.0.24}"
LAPI_PORT="${CROWDSEC_LAPI_PORT:-8084}"
METRICS_HOST="${CROWDSEC_METRICS_BIND_ADDRESS:-172.17.0.24}"
METRICS_PORT="${CROWDSEC_METRICS_PORT:-6060}"
DISABLED_SCENARIO="firewallservices/pf-scan-multi_ports"
BOUNCER_NAME="PFSENSE_FIREWALL"
CUTOVER_REQUIRED=true
[[ "${MODE}" == "--runtime" ]] && CUTOVER_REQUIRED=false

failures=0
warnings=0

ok() { printf 'OK: %s\n' "$*"; }
warn() { warnings=$((warnings + 1)); printf 'WARNING: %s\n' "$*" >&2; }
error() { failures=$((failures + 1)); printf 'ERROR: %s\n' "$*" >&2; }

for command in curl docker jq midclt ss stat grep timeout sed awk tail; do
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
  [[ "${runtime_health}" == "healthy" ]] ||
    error "CrowdSec container health is ${runtime_health:-unknown}; expected healthy"
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

printf '\n==> Cutover credential readiness\n'
if [[ "${CUTOVER_REQUIRED}" != true ]]; then
  printf 'crowdsec_cutover_credentials=deferred_runtime_only\n'
elif [[ ! -r "${SECRET_FILE}" ]]; then
  error "pfSense bouncer secret file is missing or unreadable: ${SECRET_FILE}"
else
  secret_mode="$(stat -c '%a' "${SECRET_FILE}" 2>/dev/null || true)"
  printf 'crowdsec_secret_file=%s mode=%s\n' "${SECRET_FILE}" "${secret_mode:-unknown}"
  [[ "${secret_mode}" == "600" ]] || error "CrowdSec secret file must be mode 0600"
  if grep -Eq '^BOUNCER_KEY_PFSENSE_FIREWALL=.+

printf '\n==> pfSense log acquisition via Loki\n'
if [[ -n "${container_id:-}" ]] &&
  timeout 12 docker exec "${container_id}" grep -q 'source: loki' /etc/crowdsec/acquis.d/security.yaml 2>/dev/null &&
  timeout 12 docker exec "${container_id}" grep -q 'job="pfsense", device="pfsense"' /etc/crowdsec/acquis.d/security.yaml 2>/dev/null; then
  ok "CrowdSec runtime acquisition uses the canonical pfSense Loki stream"
else
  error "CrowdSec runtime acquisition is not yet using the canonical pfSense Loki stream"
fi

loki_ready_status="$(
  curl --silent --show-error --connect-timeout 4 --max-time 10
    --output /dev/null --write-out '%{http_code}'
    "${LOKI_URL%/}/ready" 2>/dev/null || true
)"
if [[ "${loki_ready_status}" == "200" ]]; then
  ok "Loki readiness: HTTP 200"
else
  error "Loki readiness failed: HTTP ${loki_ready_status:-none}"
fi

loki_probe="$(mktemp)"
trap 'rm -f "${loki_probe}"' EXIT
if curl --silent --show-error --get --connect-timeout 4 --max-time 12
  --data-urlencode 'query={job="pfsense",device="pfsense"}'
  --data-urlencode "since=${PFSENSE_LOG_LOOKBACK}"
  --data-urlencode 'limit=1'
  --data-urlencode 'direction=backward'
  --output "${loki_probe}"
  "${LOKI_URL%/}/loki/api/v1/query_range" 2>/dev/null &&
  jq -e '.status == "success" and (.data.result | length) > 0' "${loki_probe}" >/dev/null 2>&1; then
  ok "fresh pfSense events are queryable in Loki (lookback ${PFSENSE_LOG_LOOKBACK})"
else
  error "no pfSense Loki event observed in lookback ${PFSENSE_LOG_LOOKBACK}"
fi

printf '\n==> Central LAPI bouncer registration\n'
if [[ "${CUTOVER_REQUIRED}" != true ]]; then
  printf 'crowdsec_bouncer_registration=deferred_runtime_only\n'
elif [[ -n "${container_id:-}" ]]; then
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
