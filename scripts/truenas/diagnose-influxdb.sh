#!/usr/bin/env bash
# Read-only InfluxDB health proof: TrueNAS + Docker + host/container HTTP.
# Scrape errors are aggregated, never dump raw logs (which may contain tokens).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"

APP_ID="${INFLUXDB_APP_ID:-influxdb}"
CONTAINER="${INFLUXDB_CONTAINER:-influxdb}"
HOST_URL="${INFLUXDB_HOST_URL:-http://127.0.0.1:31055}"
INTERNAL_URL="${INFLUXDB_INTERNAL_URL:-http://127.0.0.1:8086}"
COLOR_MODE=auto
ICON_MODE=auto
while (($#)); do
  case "$1" in
    --check) shift ;;
    --color) [[ $# -ge 2 ]] || exit 2; COLOR_MODE="$2"; shift 2 ;;
    --color=*) COLOR_MODE="${1#*=}"; shift ;;
    --icons) [[ $# -ge 2 ]] || exit 2; ICON_MODE="$2"; shift 2 ;;
    --icons=*) ICON_MODE="${1#*=}"; shift ;;
    *) echo 'Usage: diagnose-influxdb.sh --check [--color auto|always|never] [--icons auto|always|never]' >&2; exit 2 ;;
  esac
done
diag_ui_init "${COLOR_MODE}" "${ICON_MODE}" || exit 2
require_root 'run with sudo'
require_commands curl docker jq midclt
failures=0

diag_section '' 'InfluxDB readiness (read-only)'
app_state="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq -er 'if length == 1 then .[0].state else "MISSING" end' 2>/dev/null)" || app_state='UNKNOWN'
if [[ "${app_state}" == RUNNING ]]; then diag_ok "TrueNAS ${APP_ID}=RUNNING"
else diag_fail "TrueNAS ${APP_ID}=${app_state}"; failures=$((failures + 1)); fi

row="$(docker inspect "${CONTAINER}" |
  jq -er '.[0] | [(.State.Status//"unknown"),(.State.Health.Status//"none"),(.RestartCount//0)] | @tsv' 2>/dev/null)" || row=''
if [[ -z "${row}" ]]; then
  diag_fail 'Docker InfluxDB metadata unavailable'
  failures=$((failures + 1))
else
  IFS=$'\t' read -r state health restarts <<<"${row}"
  if [[ "${state}" == running && "${health}" == healthy ]]; then
    diag_ok "Docker running/healthy restarts=${restarts}"
  else
    diag_fail "Docker state=${state} health=${health}"
    failures=$((failures + 1))
  fi
fi

probe() {
  local label="$1" url="$2" payload
  if ! payload="$(curl --fail --silent --show-error --connect-timeout 3 --max-time 8 "${url}/health" 2>/dev/null)"; then
    diag_fail "${label} HTTP unavailable"
    failures=$((failures + 1))
    return
  fi
  if jq -e 'type=="object" and (.status=="pass" or .status=="ok" or .status=="ready")' <<<"${payload}" >/dev/null 2>&1; then
    diag_ok "${label} ready for queries and writes"
  else
    diag_fail "${label} returned invalid health JSON"
    failures=$((failures + 1))
  fi
}
probe host "${HOST_URL}"

if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  if docker exec "${CONTAINER}" curl --fail --silent --max-time 8 "${INTERNAL_URL}/health" 2>/dev/null |
       jq -e 'type=="object" and (.status=="pass" or .status=="ok" or .status=="ready")' >/dev/null 2>&1; then
    diag_ok 'Container-internal HTTP/JSON readiness'
  else
    diag_fail 'Container-internal HTTP/JSON readiness unavailable'
    failures=$((failures + 1))
  fi

  # Fixed-category, last 100 entries; private log messages are not echoed.
  # A healthy database is not proof that configured scrape targets work.
  scrape_failed_count="$(docker logs --tail 100 "${CONTAINER}" 2>&1 |
     grep -Ec 'Unable to gather.*(connection refused|connect:|timeout)' || true)"
  if [[ "${scrape_failed_count}" =~ ^[0-9]+$ && "${scrape_failed_count}" -gt 0 ]]; then
    diag_warn "Influx scraper connection failures in last 100 lines=${scrape_failed_count}"
    diag_info 'Check stale target :30115 in InfluxDB scraper configuration; DB remains ready.'
  else
    diag_ok 'No recent scrape connection errors in sample'
  fi
fi

printf '\n'
if ((failures > 0)); then
  diag_fail "InfluxDB acceptance failed (${failures} mandatory checks)"
  exit 1
fi
if ((DIAG_WARNINGS > 0)); then
  diag_warn 'InfluxDB API healthy; ingestion target(s) require repair.'
else
  diag_ok 'InfluxDB ready; no sampled ingestion anomaly.'
fi
