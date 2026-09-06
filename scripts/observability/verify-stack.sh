#!/usr/bin/env bash
set -euo pipefail

strict=false
if [[ "${1:-}" == "--strict" ]]; then
  strict=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--strict]" >&2
  exit 2
fi

OBSERVABILITY_HOST="${OBSERVABILITY_HOST:-172.17.0.24}"
PFSENSE_TARGET="${PFSENSE_TARGET:-172.17.0.1:10443}"

GRAFANA_URL="${GRAFANA_URL:-http://${OBSERVABILITY_HOST}:30037}"
ALLOY_URL="${ALLOY_URL:-http://${OBSERVABILITY_HOST}:12345}"
LOKI_URL="${LOKI_URL:-http://${OBSERVABILITY_HOST}:3100}"
MIMIR_URL="${MIMIR_URL:-http://${OBSERVABILITY_HOST}:9009}"
TEMPO_URL="${TEMPO_URL:-http://${OBSERVABILITY_HOST}:3200}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://${OBSERVABILITY_HOST}:9090}"
PFSENSE_EXPORTER_URL="${PFSENSE_EXPORTER_URL:-http://${OBSERVABILITY_HOST}:9945}"

errors=0
warnings=0
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

ok() { printf '✅ %s\n' "$*"; }
warn() {
  printf '⚠️  %s\n' "$*" >&2
  warnings=$((warnings + 1))
}
fail() {
  printf '❌ %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_command() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "command available: $1"
  else
    fail "missing command: $1"
  fi
}

check_http_200() {
  local name="$1" url="$2" body="${tmp_dir}/body-${RANDOM}"
  local status
  status="$(curl --silent --show-error --connect-timeout 4 --max-time 12     --output "${body}" --write-out '%{http_code}' "${url}" || true)"
  if [[ "${status}" == "200" ]]; then
    ok "${name} functional endpoint: ${url}"
    return 0
  fi
  fail "${name} endpoint failed: ${url} (HTTP ${status:-none})"
  return 1
}

check_grafana_health() {
  local body="${tmp_dir}/grafana-health.json"
  local status
  status="$(curl --silent --show-error --connect-timeout 4 --max-time 12     --output "${body}" --write-out '%{http_code}'     "${GRAFANA_URL%/}/api/health" || true)"
  if [[ "${status}" != "200" ]]; then
    fail "Grafana /api/health failed (HTTP ${status:-none})"
    return
  fi
  if jq -e '.database == "ok"' "${body}" >/dev/null 2>&1; then
    ok "Grafana API and database are healthy"
  else
    fail "Grafana returned HTTP 200 but database health is not ok"
  fi
}

check_exporter_target() {
  local body="${tmp_dir}/pfsense-exporter.metrics"
  local status
  status="$(curl --silent --show-error --get --connect-timeout 4 --max-time 30     --data-urlencode "target=${PFSENSE_TARGET}"     --output "${body}" --write-out '%{http_code}'     "${PFSENSE_EXPORTER_URL%/}/metrics" || true)"
  if [[ "${status}" != "200" ]]; then
    fail "pfSense exporter could not scrape ${PFSENSE_TARGET} (HTTP ${status:-none})"
    return
  fi
  if grep -Eq '^pfsense_system_[a-zA-Z0-9_:]+' "${body}"; then
    ok "pfSense exporter returned pfSense system metrics"
  else
    fail "pfSense exporter returned HTTP 200 without pfSense system metrics"
  fi
}

check_prom_query() {
  local name="$1" base_url="$2" query="$3" body="${tmp_dir}/query-${RANDOM}.json"
  local status
  status="$(curl --silent --show-error --get --connect-timeout 4 --max-time 12     --data-urlencode "query=${query}"     --output "${body}" --write-out '%{http_code}'     "${base_url}" || true)"
  if [[ "${status}" != "200" ]]; then
    fail "${name} query failed (HTTP ${status:-none})"
    return
  fi
  if jq -e '
    .status == "success"
    and (.data.result | length) > 0
    and any(.data.result[]; .value[1] == "1")
  ' "${body}" >/dev/null 2>&1; then
    ok "${name}: pfSense exporter scrape is up"
  else
    fail "${name}: up{job=\"pfsense_exporter\"} is not 1"
  fi
}

grafana_api_get() {
  local path="$1" body="$2"
  curl --silent --show-error --connect-timeout 4 --max-time 12     --header "Authorization: Bearer ${GRAFANA_SERVICE_ACCOUNT_TOKEN}"     --output "${body}" --write-out '%{http_code}'     "${GRAFANA_URL%/}${path}" || true
}

check_grafana_integrations() {
  if [[ -z "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}" ]]; then
    if [[ "${strict}" == "true" ]]; then
      fail "GRAFANA_SERVICE_ACCOUNT_TOKEN is required in --strict mode"
    else
      warn "GRAFANA_SERVICE_ACCOUNT_TOKEN not set; skipping authenticated datasource/dashboard checks"
    fi
    return
  fi

  local uid body status
  for uid in loki mimir tempo; do
    body="${tmp_dir}/grafana-datasource-${uid}.json"
    status="$(grafana_api_get "/api/datasources/uid/${uid}/health" "${body}")"
    if [[ "${status}" == "200" ]] && jq -e '
      (.status // "") | ascii_downcase == "ok"
    ' "${body}" >/dev/null 2>&1; then
      ok "Grafana datasource healthy: ${uid}"
    else
      fail "Grafana datasource health failed: ${uid} (HTTP ${status:-none})"
    fi
  done

  local dashboard_uids=(
    pfsense_system
    adkq2ms
    pfsense_gateways
    pfsense-traffic
    pfsense_firewall
    pfsense_services
    pfsense_carp
    pfsense_logs
  )
  for uid in "${dashboard_uids[@]}"; do
    body="${tmp_dir}/grafana-dashboard-${uid}.json"
    status="$(grafana_api_get "/api/dashboards/uid/${uid}" "${body}")"
    if [[ "${status}" == "200" ]] && jq -e '.dashboard.uid != null' "${body}" >/dev/null 2>&1; then
      ok "Grafana dashboard provisioned: ${uid}"
    else
      fail "Grafana dashboard missing/unreadable: ${uid} (HTTP ${status:-none})"
    fi
  done
}

printf '🔎 Homelab observability integration preflight\n'
printf 'Host: %s | pfSense target: %s\n\n' "${OBSERVABILITY_HOST}" "${PFSENSE_TARGET}"

for command in curl grep jq mktemp; do
  require_command "${command}"
done

if ((errors > 0)); then
  printf '\n❌ Missing local dependencies; stopping before network checks.\n' >&2
  exit 1
fi

printf '\n🩺 Service readiness\n'
check_grafana_health
check_http_200 "Alloy readiness" "${ALLOY_URL%/}/-/ready"
check_http_200 "Alloy component health" "${ALLOY_URL%/}/-/healthy"
check_http_200 "Loki readiness" "${LOKI_URL%/}/ready"
check_http_200 "Mimir readiness" "${MIMIR_URL%/}/ready"
check_http_200 "Tempo readiness" "${TEMPO_URL%/}/ready"
check_http_200 "Prometheus readiness" "${PROMETHEUS_URL%/}/-/ready"

printf '\n🔥 pfSense metrics path\n'
check_exporter_target
check_prom_query   "Prometheus"   "${PROMETHEUS_URL%/}/api/v1/query"   'up{job="pfsense_exporter"}'
check_prom_query   "Mimir"   "${MIMIR_URL%/}/prometheus/api/v1/query"   'up{job="pfsense_exporter"}'

printf '\n📊 Grafana integration\n'
check_grafana_integrations

printf '\n'
if ((errors > 0)); then
  printf '❌ Observability preflight failed: %d error(s), %d warning(s).\n'     "${errors}" "${warnings}" >&2
  exit 1
fi

printf '✅ Observability preflight passed with %d warning(s).\n' "${warnings}"
