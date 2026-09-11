#!/usr/bin/env bash
set -euo pipefail

MODE="check"
SSH_TARGET="${PFSENSE_SSH_TARGET:-root@172.17.0.1}"
SSH_PORT="${PFSENSE_SSH_PORT:-}"
API_URL="${PFSENSE_API_URL:-https://home.albandrieu.com:10443}"
LAN_API_URL="${PFSENSE_LAN_API_URL:-https://172.17.0.1:10443}"
PROBE_SOURCES="${PFSENSE_PROBE_SOURCES:-172.17.0.24 172.17.0.57}"
UNBLOCK_SOURCES=false
API_ONLY=false
REPORT="${PFSENSE_RECOVERY_REPORT:-/tmp/pfsense-recovery-$(date +%Y%m%d-%H%M%S).log}"

usage() {
  cat <<'USAGE'
Usage: scripts/pfsense/diagnose-recover.sh [options]

Canonical pfSense diagnosis/recovery helper for nabla-compose. Run it from the
workstation. Read-only HTTPS/API evidence is collected even when pfSense SSH is
unreachable; SSH is required only for deep appliance diagnostics and --apply.

Options:
  --check                   Read-only diagnosis (default).
  --api-only                Skip SSH and collect HTTPS/API evidence only.
  --apply                   Run narrowly scoped recovery over SSH after probes.
  --unblock-sources         With --apply only: delete exact host entries from
                            proven snort2c/pfBlockerNG dynamic tables.
  --target USER@HOST        SSH target (default: root@172.17.0.1).
  --port PORT               Optional SSH port; otherwise SSH config/default applies.
  --api-url URL             Hostname/public HTTPS URL.
  --lan-api-url URL         Direct LAN HTTPS URL used as a second vantage point.
  --probe-sources "IP ..."  Exact source IPs to attribute/unblock.
  --report PATH             Local report path.
  -h, --help                Show this help.

Environment:
  PFSENSE_POSTURE_API_KEY   Optional read-only API key. It stays on the caller;
                            it is never sent through SSH or printed.
  PFSENSE_SSH_TARGET        Default SSH target override.
  PFSENSE_SSH_PORT          Optional SSH port override.

Recommended sequence:
  1. --check
  2. review HTTPS/API and, when reachable, SSH evidence
  3. --apply only when recovery is justified
  4. --apply --unblock-sources only after an exact BLOCK_MATCH
USAGE
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

while (($# > 0)); do
  case "$1" in
    --check)
      MODE="check"
      ;;
    --api-only)
      API_ONLY=true
      ;;
    --apply)
      MODE="apply"
      ;;
    --unblock-sources)
      UNBLOCK_SOURCES=true
      ;;
    --target)
      shift
      (($# > 0)) || fail "--target requires USER@HOST"
      SSH_TARGET="$1"
      ;;
    --port)
      shift
      (($# > 0)) || fail "--port requires a port"
      SSH_PORT="$1"
      ;;
    --api-url)
      shift
      (($# > 0)) || fail "--api-url requires URL"
      API_URL="$1"
      ;;
    --lan-api-url)
      shift
      (($# > 0)) || fail "--lan-api-url requires URL"
      LAN_API_URL="$1"
      ;;
    --probe-sources)
      shift
      (($# > 0)) || fail "--probe-sources requires a space-separated IP list"
      PROBE_SOURCES="$1"
      ;;
    --report)
      shift
      (($# > 0)) || fail "--report requires PATH"
      REPORT="$1"
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
  shift
done

[[ "${API_URL}" == https://* ]] || fail "--api-url must use https://"
[[ "${LAN_API_URL}" == https://* ]] || fail "--lan-api-url must use https://"
if [[ "${UNBLOCK_SOURCES}" == true && "${MODE}" != "apply" ]]; then
  fail "--unblock-sources requires --apply"
fi
if [[ "${API_ONLY}" == true && "${MODE}" == "apply" ]]; then
  fail "--api-only cannot be combined with --apply"
fi
if [[ -n "${SSH_PORT}" && ! "${SSH_PORT}" =~ ^[0-9]+$ ]]; then
  fail "--port must be numeric"
fi
for source in ${PROBE_SOURCES}; do
  [[ "${source}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "invalid IPv4 probe source: ${source}"
done
for command in curl jq tee grep awk date mktemp; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
if [[ "${API_ONLY}" != true || "${MODE}" == "apply" ]]; then
  command -v ssh >/dev/null 2>&1 || fail "ssh is required"
fi

mkdir -p "$(dirname "${REPORT}")"
: >"${REPORT}"

log() {
  printf '%s\n' "$*" | tee -a "${REPORT}"
}

probe_url() {
  local label="$1"
  local url="$2"
  local insecure="$3"
  local -a tls_args=()
  local output
  if [[ "${insecure}" == true ]]; then
    tls_args=(-k)
  fi
  if output="$(curl "${tls_args[@]}" --fail --silent --show-error \
    --connect-timeout 5 --max-time 15 -o /dev/null \
    -w "${label} http=%{http_code} peer=%{remote_ip} tls=%{ssl_verify_result} time=%{time_total}" \
    "${url%/}/" 2>&1)"; then
    log "${output}"
    return 0
  fi
  log "${label} ERROR ${output}"
  return 1
}

API_HEADER_FILE=""
cleanup() {
  [[ -z "${API_HEADER_FILE}" ]] || rm -f "${API_HEADER_FILE}"
}
trap cleanup EXIT

prepare_api_header() {
  [[ -n "${PFSENSE_POSTURE_API_KEY:-}" ]] || return 1
  API_HEADER_FILE="$(mktemp)"
  chmod 600 "${API_HEADER_FILE}"
  {
    printf 'X-API-Key: %s\n' "${PFSENSE_POSTURE_API_KEY}"
    printf 'Accept: application/json\n'
  } >"${API_HEADER_FILE}"
}

probe_api() {
  local label="$1"
  local base_url="$2"
  local insecure="$3"
  local endpoint="$4"
  local -a tls_args=()
  local body http_code
  body="$(mktemp)"
  if [[ "${insecure}" == true ]]; then
    tls_args=(-k)
  fi

  http_code="$(curl "${tls_args[@]}" --silent --show-error \
    --connect-timeout 5 --max-time 15 \
    -o "${body}" -w '%{http_code}' \
    --header "@${API_HEADER_FILE}" \
    "${base_url%/}${endpoint}" 2>>"${REPORT}" || true)"

  if [[ "${http_code}" == "200" ]] && jq -e '.code == 200 and .status == "ok"' "${body}" >/dev/null 2>&1; then
    local summary
    summary="$(jq -c '{code,status,response_id,data_type:(.data|type),count:(if (.data|type)=="array" then (.data|length) else null end)}' "${body}")"
    log "${label} endpoint=${endpoint} http=${http_code} ${summary}"
    rm -f "${body}"
    return 0
  fi

  log "${label} endpoint=${endpoint} http=${http_code:-000} ERROR"
  jq -c '{code,status,response_id,message}' "${body}" 2>/dev/null | tee -a "${REPORT}" || true
  rm -f "${body}"
  return 1
}

log "pfSense recovery mode=${MODE} target=${SSH_TARGET} api=${API_URL} lan_api=${LAN_API_URL} sources=${PROBE_SOURCES}"
log "Local report: ${REPORT}"
log ""
log "==> HTTPS/API vantage points"

api_failures=0
probe_url "ui_hostname" "${API_URL}" false || api_failures=$((api_failures + 1))
probe_url "ui_lan" "${LAN_API_URL}" true || api_failures=$((api_failures + 1))

if prepare_api_header; then
  endpoints=(
    /api/v2/system/version
    /api/v2/status/services
    /api/v2/services/dns_resolver/settings
    /api/v2/system/dns
  )
  for endpoint in "${endpoints[@]}"; do
    probe_api "api_hostname" "${API_URL}" false "${endpoint}" || api_failures=$((api_failures + 1))
  done
  probe_api "api_lan" "${LAN_API_URL}" true /api/v2/system/version || api_failures=$((api_failures + 1))
else
  log "WARN: PFSENSE_POSTURE_API_KEY unset: authenticated API evidence not evaluated"
fi

if [[ "${API_ONLY}" == true ]]; then
  if ((api_failures > 0)); then
    fail "API-only diagnosis completed with ${api_failures} failed probe(s)"
  fi
  log "OK: API-only diagnosis completed"
  exit 0
fi

SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=2
)
if [[ -n "${SSH_PORT}" ]]; then
  SSH_OPTS+=(-p "${SSH_PORT}")
fi

log ""
log "==> Deep appliance evidence over SSH"
ssh_status=0
set +e
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" /bin/sh -s -- \
  "${MODE}" "${UNBLOCK_SOURCES}" "${PROBE_SOURCES}" <<'REMOTE' 2>&1 | tee -a "${REPORT}"
set -u
MODE="$1"
UNBLOCK_SOURCES="$2"
shift 2
PROBE_SOURCES="$*"

section() { printf '\n==> %s\n' "$1"; }
run_optional() { "$@" 2>&1 || true; }

section "Snapshot"
date
uptime
hostname
run_optional sockstat -4 -6 -l
run_optional df -h
run_optional df -i
run_optional swapinfo -h
printf '\nTop RSS processes:\n'
ps axo pid,rss,vsz,pcpu,pmem,command 2>/dev/null | sort -nr -k2 | head -25 || true
printf '\nKernel memory/reclaim evidence:\n'
dmesg 2>/dev/null | egrep -i 'killed|failed to reclaim|waited too long|out of swap|out of memory|oom' | tail -80 || true

section "nginx / PHP-FPM / webConfigurator"
pgrep -laf 'nginx|php-fpm' 2>/dev/null || true
sockstat 2>/dev/null | egrep 'nginx|php-fpm|:443|:10443' || true
if command -v nginx >/dev/null 2>&1; then run_optional nginx -t; fi
if command -v php-fpm >/dev/null 2>&1; then
  run_optional php-fpm -t
elif [ -x /usr/local/sbin/php-fpm ]; then
  run_optional /usr/local/sbin/php-fpm -t
fi
tail -n 450 /var/log/system.log 2>/dev/null | egrep -i 'nginx|php|fpm|webconfig|fatal|segfault|killed|memory|502|upstream|error' | tail -180 || true

section "Unbound"
UNBOUND_HEALTHY=false
pgrep -laf '[u]nbound' 2>/dev/null || true
sockstat 2>/dev/null | grep ':53' | head -30 || true
if command -v unbound-control >/dev/null 2>&1 && [ -f /var/unbound/unbound.conf ]; then
  if unbound-control -c /var/unbound/unbound.conf status 2>&1; then
    UNBOUND_HEALTHY=true
  fi
  unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | egrep '^mem\.' | head -80 || true
fi
printf 'unbound_control_healthy=%s\n' "${UNBOUND_HEALTHY}"

section "Snort / pfBlockerNG / PF attribution"
pgrep -laf 'snort|pfblocker|pfb_' 2>/dev/null || true
TABLES="$(pfctl -s Tables 2>/dev/null | egrep '^(snort2c|pfB_|pfb_)' || true)"
printf 'candidate_tables:\n%s\n' "${TABLES:-<none>}"
BLOCK_MATCH_COUNT=0
for source in ${PROBE_SOURCES}; do
  for table in ${TABLES}; do
    if pfctl -t "${table}" -T show 2>/dev/null | awk -v ip="${source}" '$1 == ip {found=1} END {exit !found}'; then
      BLOCK_MATCH_COUNT=$((BLOCK_MATCH_COUNT + 1))
      echo "BLOCK_MATCH table=${table} source=${source} exact=yes"
      if [ "${MODE}" = apply ] && [ "${UNBLOCK_SOURCES}" = true ]; then
        case "${table}" in
          snort2c | pfB_* | pfb_*)
            echo "UNBLOCK_ACTION table=${table} source=${source}"
            pfctl -t "${table}" -T delete "${source}" 2>&1 || true
            ;;
        esac
      fi
    fi
  done
done
printf 'block_match_count=%s\n' "${BLOCK_MATCH_COUNT}"

if [ "${MODE}" = apply ]; then
  section "Targeted recovery actions"
  /etc/rc.php-fpm_restart 2>&1 || true
  sleep 2
  /etc/rc.restart_webgui 2>&1 || true
  sleep 3
  if [ "${UNBOUND_HEALTHY}" != true ]; then
    if [ -x /usr/local/sbin/pfSsh.php ]; then
      /usr/local/sbin/pfSsh.php playback svc restart unbound 2>&1 || true
    elif [ -x /etc/rc.d/unbound ]; then
      /etc/rc.d/unbound restart 2>&1 || true
    fi
  fi
else
  section "No mutation"
  echo 'check mode: no service restart and no PF table mutation performed'
fi
REMOTE
ssh_status=${PIPESTATUS[0]}
set -e

if ((ssh_status != 0)); then
  if [[ "${MODE}" == "apply" ]]; then
    fail "SSH diagnostics/recovery failed with status ${ssh_status}; no successful apply can be claimed"
  fi
  warn "SSH unavailable (status ${ssh_status}); HTTPS/API evidence above remains valid, but deep appliance diagnostics were not collected"
  log "WARN: SSH unavailable; use --port/SSH config if pfSense SSH is not on port 22, or --api-only when SSH is intentionally filtered"
else
  log "OK: SSH appliance diagnostics completed"
fi

if ((api_failures > 0)); then
  fail "diagnosis completed with ${api_failures} failed HTTPS/API probe(s)"
fi

log "OK: pfSense HTTPS/API diagnosis completed"
