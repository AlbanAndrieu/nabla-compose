#!/usr/bin/env bash
set -euo pipefail

mode="all"
case "${1:-}" in
  "") ;;
  --synthetic-only) mode="synthetic" ;;
  --live-only) mode="live" ;;
  *)
    echo "usage: $0 [--synthetic-only|--live-only]" >&2
    exit 2
    ;;
esac

OBSERVABILITY_HOST="${OBSERVABILITY_HOST:-172.17.0.24}"
ALLOY_URL="${ALLOY_URL:-http://${OBSERVABILITY_HOST}:12345}"
LOKI_URL="${LOKI_URL:-http://${OBSERVABILITY_HOST}:3100}"
ALLOY_SYSLOG_HOST="${ALLOY_SYSLOG_HOST:-${OBSERVABILITY_HOST}}"
ALLOY_SYSLOG_UDP_PORT="${ALLOY_SYSLOG_UDP_PORT:-1514}"
PFSENSE_SYSLOG_SOURCE_IP="${PFSENSE_SYSLOG_SOURCE_IP:-172.17.0.1}"
PFSENSE_LOG_LOOKBACK="${PFSENSE_LOG_LOOKBACK:-30m}"
SYSLOG_SMOKE_TIMEOUT="${SYSLOG_SMOKE_TIMEOUT:-20}"

errors=0
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

ok() { printf '✅ %s\n' "$*"; }
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
  local name="$1" url="$2"
  local status
  status="$(curl --silent --show-error --connect-timeout 4 --max-time 10     --output /dev/null --write-out '%{http_code}' "${url}" || true)"
  if [[ "${status}" == "200" ]]; then
    ok "${name}: HTTP 200"
  else
    fail "${name}: HTTP ${status:-none}"
  fi
}

loki_query() {
  local query="$1" since="$2" output="$3"
  curl --silent --show-error --get --connect-timeout 4 --max-time 12     --data-urlencode "query=${query}"     --data-urlencode "since=${since}"     --data-urlencode "limit=20"     --data-urlencode "direction=backward"     --output "${output}"     "${LOKI_URL%/}/loki/api/v1/query_range"
}

send_rfc5424_smoke() {
  local marker="$1"
  local timestamp message
  timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  message="<14>1 ${timestamp} observability-smoke nabla-smoke $$ - - ${marker}"

  python3 - "${ALLOY_SYSLOG_HOST}" "${ALLOY_SYSLOG_UDP_PORT}" "${message}" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
payload = sys.argv[3].encode("utf-8")
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.sendto(payload, (host, port))
PY
}

verify_synthetic() {
  local marker
  local output="${tmp_dir}/synthetic.json"
  marker="nabla-observability-smoke-$(date +%s)-$"
  local waited=0
  local query

  query='{job="pfsense",app="nabla-smoke"} |= "'"${marker}"'"'

  printf '\n🧪 Synthetic RFC5424 -> Alloy -> Loki\n'
  send_rfc5424_smoke "${marker}"
  ok "sent one RFC5424 UDP smoke record to ${ALLOY_SYSLOG_HOST}:${ALLOY_SYSLOG_UDP_PORT}"

  while ((waited < SYSLOG_SMOKE_TIMEOUT)); do
    if loki_query "${query}" "5m" "${output}" 2>/dev/null &&
      jq -e '.status == "success" and (.data.result | length) > 0'         "${output}" >/dev/null 2>&1; then
      ok "synthetic syslog traversed Alloy and is queryable in Loki"
      return
    fi
    sleep 2
    waited=$((waited + 2))
  done

  fail "synthetic RFC5424 record did not appear in Loki within ${SYSLOG_SMOKE_TIMEOUT}s"
}

verify_live_pfsense() {
  local output="${tmp_dir}/pfsense-live.json"
  local query="{job=\"pfsense\",sender=\"${PFSENSE_SYSLOG_SOURCE_IP}\"}"

  printf '\n🔥 Real pfSense -> Alloy -> Loki\n'
  if ! loki_query "${query}" "${PFSENSE_LOG_LOOKBACK}" "${output}" 2>/dev/null; then
    fail "Loki query for pfSense sender failed"
    return
  fi

  if jq -e '.status == "success" and (.data.result | length) > 0'     "${output}" >/dev/null 2>&1; then
    local streams
    streams="$(jq '[.data.result[].stream] | unique | length' "${output}")"
    ok "real pfSense syslog observed from sender ${PFSENSE_SYSLOG_SOURCE_IP} (${streams} stream(s), lookback ${PFSENSE_LOG_LOOKBACK})"
  else
    fail "no real pfSense syslog from sender ${PFSENSE_SYSLOG_SOURCE_IP} in the last ${PFSENSE_LOG_LOOKBACK}"
  fi
}

printf '🔎 pfSense syslog integration verification\n'
printf 'Alloy UDP: %s:%s | expected pfSense sender: %s\n\n'   "${ALLOY_SYSLOG_HOST}" "${ALLOY_SYSLOG_UDP_PORT}" "${PFSENSE_SYSLOG_SOURCE_IP}"

for command in curl date jq mktemp python3; do
  require_command "${command}"
done

if ((errors > 0)); then
  printf '\n❌ Missing local dependencies; stopping before network checks.\n' >&2
  exit 1
fi

check_http_200 "Alloy readiness" "${ALLOY_URL%/}/-/ready"
check_http_200 "Alloy component health" "${ALLOY_URL%/}/-/healthy"
check_http_200 "Loki readiness" "${LOKI_URL%/}/ready"

if ((errors > 0)); then
  printf '\n❌ Core log services are not healthy; syslog tests were not started.\n' >&2
  exit 1
fi

if [[ "${mode}" != "live" ]]; then
  verify_synthetic
fi
if [[ "${mode}" != "synthetic" ]]; then
  verify_live_pfsense
fi

printf '\n'
if ((errors > 0)); then
  printf '❌ pfSense syslog verification failed with %d error(s).\n' "${errors}" >&2
  printf 'Inspect: docker logs alloy --since 10m ; docker logs loki --since 10m\n' >&2
  exit 1
fi

printf '✅ pfSense syslog integration is healthy.\n'
