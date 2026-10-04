#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IDENTITY_HELPER="${SCRIPT_DIR}/manage-api-identities.php"

MODE="check"
SSH_TARGET="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
SSH_PORT="${PFSENSE_SSH_PORT:-}"
API_URL="${PFSENSE_API_URL:-https://home.albandrieu.com:10443}"
LAN_API_URL="${PFSENSE_LAN_API_URL:-https://172.17.0.1:10443}"
FASTAPI_URL="${FASTAPI_SAMPLE_URL:-https://fastapi-sample.fastapicloud.dev}"
PROBE_SOURCES="${PFSENSE_PROBE_SOURCES:-172.17.0.24 172.17.0.57}"
AUTO_EGRESS=true
UNBLOCK_SOURCES=false
API_ONLY=false
IDENTITY_ACTION=""
IDENTITY_TARGET="all"
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
  --check-identities         SSH-only audit of fastapi_posture/fastapi_security
                            users, group membership, privileges and persisted keys.
  --apply-identities         Create missing service users (password files required)
                            and reconcile both to steady-state least privilege.
  --prepare-key-rotation ID  Prepare posture|security for key creation: remove
                            Deny Config Write and grant api-v2-auth-key-post.
  --finalize-key-rotation ID Restore posture|security to steady state after a
                            persisted key is visible: remove key POST, restore
                            Deny Config Write. Refuses finalization with zero keys.
  --target USER@HOST        SSH target/alias (default: home.albandrieu.com).
  --port PORT               Optional SSH port; otherwise SSH config/default applies.
  --api-url URL             Hostname/public HTTPS URL.
  --lan-api-url URL         Direct LAN HTTPS URL used as a second vantage point.
  --probe-sources "IP ..."  Exact source IPs to attribute/unblock.
  --fastapi-url URL         FastAPI Sample URL used to discover active egress.
  --no-auto-egress          Do not add FastAPI Sample active egress addresses.
  --report PATH             Local report path.
  -h, --help                Show this help.

Environment:
  PFSENSE_POSTURE_API_KEY   Optional posture GET-only API key. It stays on the
                            caller; it is never sent through SSH or printed.
  PFSENSE_SECURITY_API_KEY  Optional diagnostics-table GET-only API key with the
                            same secret-handling contract.
  PFSENSE_SSH_TARGET        Default SSH target override.
  PFSENSE_SSH_PORT          Optional SSH port override.
  FASTAPI_SAMPLE_URL        FastAPI Sample base URL for egress discovery.
  PFSENSE_POSTURE_PASSWORD_FILE
                            One-line password file used only when --apply-identities
                            must create a missing fastapi_posture user.
  PFSENSE_SECURITY_PASSWORD_FILE
                            One-line password file used only when --apply-identities
                            must create a missing fastapi_security user.

Recommended sequence:
  1. --check
  2. review HTTPS/API and, when reachable, SSH evidence
  3. --apply only when recovery is justified
  4. --apply --unblock-sources only after an exact BLOCK_MATCH

Identity/key lifecycle:
  --check-identities
  --prepare-key-rotation posture|security
  create the key with that service user's Basic credentials
  --finalize-key-rotation posture|security
  --check-identities
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
    --check-identities)
      IDENTITY_ACTION="check"
      IDENTITY_TARGET="all"
      ;;
    --apply-identities)
      IDENTITY_ACTION="apply"
      IDENTITY_TARGET="all"
      ;;
    --prepare-key-rotation)
      shift
      (($# > 0)) || fail "--prepare-key-rotation requires posture or security"
      IDENTITY_ACTION="prepare"
      IDENTITY_TARGET="$1"
      ;;
    --finalize-key-rotation)
      shift
      (($# > 0)) || fail "--finalize-key-rotation requires posture or security"
      IDENTITY_ACTION="finalize"
      IDENTITY_TARGET="$1"
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
    --fastapi-url)
      shift
      (($# > 0)) || fail "--fastapi-url requires URL"
      FASTAPI_URL="$1"
      ;;
    --no-auto-egress)
      AUTO_EGRESS=false
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
[[ "${FASTAPI_URL}" == https://* ]] || fail "--fastapi-url must use https://"
if [[ "${UNBLOCK_SOURCES}" == true && "${MODE}" != "apply" ]]; then
  fail "--unblock-sources requires --apply"
fi
if [[ "${API_ONLY}" == true && "${MODE}" == "apply" ]]; then
  fail "--api-only cannot be combined with --apply"
fi
if [[ -n "${IDENTITY_ACTION}" && ( "${API_ONLY}" == true || "${MODE}" == "apply" || "${UNBLOCK_SOURCES}" == true ) ]]; then
  fail "identity lifecycle options cannot be combined with --api-only, --apply, or --unblock-sources"
fi
if [[ "${IDENTITY_TARGET}" != "all" && "${IDENTITY_TARGET}" != "posture" && "${IDENTITY_TARGET}" != "security" ]]; then
  fail "identity target must be posture or security"
fi
if [[ -n "${SSH_PORT}" && ! "${SSH_PORT}" =~ ^[0-9]+$ ]]; then
  fail "--port must be numeric"
fi

password_file_b64() {
  local path="$1"
  local label="$2"
  local value=""
  [[ -n "${path}" ]] || return 0
  [[ -f "${path}" && -r "${path}" ]] || fail "${label} password file is not readable: ${path}"
  IFS= read -r value <"${path}" || true
  [[ -n "${value}" ]] || fail "${label} password file is empty: ${path}"
  if tail -n +2 "${path}" | grep -q '[^[:space:]]'; then
    fail "${label} password file must contain exactly one password line"
  fi
  printf '%s' "${value}" | base64 | tr -d '\r\n'
}

identity_ssh_preflight() {
  local resolved user port hostname
  resolved="$(ssh -G "${SSH_TARGET}" 2>/dev/null)" ||
    fail "unable to resolve SSH configuration for ${SSH_TARGET}"
  user="$(awk '$1 == "user" {print $2; exit}' <<<"${resolved}")"
  port="$(awk '$1 == "port" {print $2; exit}' <<<"${resolved}")"
  hostname="$(awk '$1 == "hostname" {print $2; exit}' <<<"${resolved}")"

  if [[ -n "${SSH_PORT}" ]]; then
    port="${SSH_PORT}"
  fi
  if [[ "${SSH_TARGET}" == *@* ]]; then
    user="${SSH_TARGET%%@*}"
  fi

  printf 'pfSense identity SSH path: user=%s host=%s port=%s\n'     "${user:-unknown}" "${hostname:-unknown}" "${port:-unknown}"

  if [[ "${user:-}" != "admin" || "${port:-}" != "9922" ]]; then
    fail "pfSense identity lifecycle must use the workstation management SSH contract admin@home.albandrieu.com:9922; current SSH resolution is ${user:-unknown}@${hostname:-unknown}:${port:-unknown}. Run from the workstation, or pass --target admin@home.albandrieu.com --port 9922 only from a host that already has the required SSH credential."
  fi
}

run_identity_admin() {
  local action="$1"
  local target="$2"
  local posture_password_b64=""
  local security_password_b64=""
  local status=0
  local -a ssh_opts=(
    -o BatchMode=yes
    -o ConnectTimeout=8
    -o ServerAliveInterval=5
    -o ServerAliveCountMax=2
    -o ControlMaster=no
    -o ControlPath=none
  )

  [[ -f "${IDENTITY_HELPER}" ]] || fail "identity helper not found: ${IDENTITY_HELPER}"
  if [[ -n "${SSH_PORT}" ]]; then
    ssh_opts+=(-p "${SSH_PORT}")
  fi
  if [[ "${action}" == "apply" ]]; then
    posture_password_b64="$(password_file_b64 "${PFSENSE_POSTURE_PASSWORD_FILE:-}" "posture")"
    security_password_b64="$(password_file_b64 "${PFSENSE_SECURITY_PASSWORD_FILE:-}" "security")"
  fi

  set +e
  {
    printf '<?php\n'
    printf "define('NABLA_IDENTITY_ACTION', '%s');\n" "${action}"
    printf "define('NABLA_IDENTITY_TARGET', '%s');\n" "${target}"
    printf "define('NABLA_POSTURE_PASSWORD_B64', '%s');\n" "${posture_password_b64}"
    printf "define('NABLA_SECURITY_PASSWORD_B64', '%s');\n" "${security_password_b64}"
    printf '?>\n'
    cat "${IDENTITY_HELPER}"
  } | ssh "${ssh_opts[@]}" "${SSH_TARGET}" /usr/local/bin/php
  status=${PIPESTATUS[1]}
  set -e
  return "${status}"
}

if [[ -n "${IDENTITY_ACTION}" ]]; then
  command -v ssh >/dev/null 2>&1 || fail "ssh is required for identity lifecycle actions"
  command -v base64 >/dev/null 2>&1 || fail "base64 is required for identity lifecycle actions"
  identity_ssh_preflight
  run_identity_admin "${IDENTITY_ACTION}" "${IDENTITY_TARGET}" ||
    fail "pfSense identity lifecycle action failed"
  exit 0
fi

for command in curl jq tee grep awk date mktemp paste; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
if [[ "${AUTO_EGRESS}" == true ]]; then
  runtime_json="$(mktemp)"
  runtime_source=""
  if curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
    "${FASTAPI_URL%/}/api/runtime/topology" -o "${runtime_json}"; then
    runtime_source="runtime-topology"
    discovered_egress="$(jq -r '.active_egress_ips[]? // empty' "${runtime_json}" | paste -sd' ' -)"
  elif curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
    "${FASTAPI_URL%/}/api/health-board" -o "${runtime_json}"; then
    runtime_source="health-board"
    discovered_egress="$(jq -r '.runtime.active_egress_ips[]? // empty' "${runtime_json}" | paste -sd' ' -)"
  else
    discovered_egress=""
  fi

  if [[ -n "${discovered_egress}" ]]; then
    printf 'FASTAPI_EGRESS=%s source=%s\n' "${discovered_egress}" "${runtime_source}"
    PROBE_SOURCES="${PROBE_SOURCES:+${PROBE_SOURCES} }${discovered_egress}"
  elif [[ -n "${runtime_source}" ]]; then
    warn "FastAPI ${runtime_source} returned no active_egress_ips"
  else
    warn "unable to discover FastAPI Sample active egress from ${FASTAPI_URL}"
  fi
  rm -f "${runtime_json}"
fi
read -r -a probe_source_array <<<"${PROBE_SOURCES}"
PROBE_SOURCES="$(printf '%s\n' "${probe_source_array[@]}" | awk 'NF && !seen[$0]++' | paste -sd' ' -)"
[[ -n "${PROBE_SOURCES}" ]] || fail "no probe sources available; use --probe-sources or enable FastAPI egress discovery"
read -r -a probe_source_array <<<"${PROBE_SOURCES}"
for source in "${probe_source_array[@]}"; do
  [[ "${source}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "invalid IPv4 probe source: ${source}"
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
    -w "${label} http=%{http_code} peer=%{remote_ip} tls_verify=%{ssl_verify_result} connect=%{time_connect}s tls=%{time_appconnect}s first=%{time_starttransfer}s total=%{time_total}s" \
    "${url%/}/" 2>&1)"; then
    log "${output}"
    return 0
  fi
  log "${label} ERROR ${output}"
  return 1
}

POSTURE_API_HEADER_FILE=""
SECURITY_API_HEADER_FILE=""
cleanup() {
  [[ -z "${POSTURE_API_HEADER_FILE}" ]] || rm -f "${POSTURE_API_HEADER_FILE}"
  [[ -z "${SECURITY_API_HEADER_FILE}" ]] || rm -f "${SECURITY_API_HEADER_FILE}"
}
trap cleanup EXIT

prepare_api_header() {
  local key="$1"
  local output_file="$2"
  [[ -n "${key}" ]] || return 1
  chmod 600 "${output_file}"
  {
    printf 'X-API-Key: %s\n' "${key}"
    printf 'Accept: application/json\n'
  } >"${output_file}"
}

probe_api() {
  local label="$1"
  local base_url="$2"
  local insecure="$3"
  local endpoint="$4"
  local expected_http="$5"
  local header_file="$6"
  local -a tls_args=()
  local body error_file meta curl_status=0
  local http_code peer time_connect time_tls time_first time_total
  body="$(mktemp)"
  error_file="$(mktemp)"
  if [[ "${insecure}" == true ]]; then
    tls_args=(-k)
  fi

  meta="$(curl "${tls_args[@]}" --silent --show-error \
    --connect-timeout 5 --max-time 15 \
    -o "${body}" \
    -w '%{http_code}|%{remote_ip}|%{time_connect}|%{time_appconnect}|%{time_starttransfer}|%{time_total}' \
    --header "@${header_file}" \
    "${base_url%/}${endpoint}" 2>"${error_file}")" || curl_status=$?
  IFS='|' read -r http_code peer time_connect time_tls time_first time_total <<<"${meta}"

  if ((curl_status != 0)); then
    local curl_error
    curl_error="$(tr '\r\n\t' '   ' <"${error_file}" | head -c 320)"
    log "${label} endpoint=${endpoint} http=${http_code:-000} curl_exit=${curl_status} peer=${peer:-unknown} connect=${time_connect:-unknown}s tls=${time_tls:-unknown}s first=${time_first:-unknown}s total=${time_total:-unknown}s ERROR"
    [[ -z "${curl_error}" ]] || log "${label} curl_error=${curl_error}"
    rm -f "${body}" "${error_file}"
    return 1
  fi

  if [[ "${http_code}" == "${expected_http}" ]]; then
    if [[ "${expected_http}" != "200" ]] || jq -e '.code == 200 and .status == "ok"' "${body}" >/dev/null 2>&1; then
      local summary=""
      if [[ -s "${body}" ]]; then
        summary="$(jq -c '{code,status,response_id,data_type:(.data|type),count:(if (.data|type)=="array" then (.data|length) else null end)}' "${body}" 2>/dev/null || true)"
      fi
      log "${label} endpoint=${endpoint} http=${http_code} expected=${expected_http} peer=${peer:-unknown} connect=${time_connect:-unknown}s tls=${time_tls:-unknown}s first=${time_first:-unknown}s total=${time_total:-unknown}s${summary:+ ${summary}}"
      rm -f "${body}" "${error_file}"
      return 0
    fi
  fi

  log "${label} endpoint=${endpoint} http=${http_code:-000} expected=${expected_http} peer=${peer:-unknown} connect=${time_connect:-unknown}s tls=${time_tls:-unknown}s first=${time_first:-unknown}s total=${time_total:-unknown}s ERROR"
  jq -c '{code,status,response_id,message}' "${body}" 2>/dev/null | tee -a "${REPORT}" || true
  rm -f "${body}" "${error_file}"
  return 1
}

log "pfSense recovery mode=${MODE} target=${SSH_TARGET} api=${API_URL} lan_api=${LAN_API_URL} fastapi=${FASTAPI_URL} sources=${PROBE_SOURCES}"
log "Local report: ${REPORT}"
log ""
log "==> HTTPS/API vantage points"

api_failures=0
auth_lockout_risk=false
ui_hostname_ok=true
ui_lan_ok=true
probe_url "ui_hostname" "${API_URL}" false || {
  ui_hostname_ok=false
  api_failures=$((api_failures + 1))
}
probe_url "ui_lan" "${LAN_API_URL}" true || {
  ui_lan_ok=false
  api_failures=$((api_failures + 1))
}

if [[ -n "${PFSENSE_POSTURE_API_KEY:-}" ]]; then
  POSTURE_API_HEADER_FILE="$(mktemp)"
  prepare_api_header "${PFSENSE_POSTURE_API_KEY}" "${POSTURE_API_HEADER_FILE}"
  posture_endpoints=(
    /api/v2/system/version
    /api/v2/status/services
    /api/v2/services/dns_resolver/settings
    /api/v2/system/dns
  )
  # KeyAuth failures can feed pfSense REST API Login Protection/sshguard.
  # Probe one harmless endpoint first and fail closed on 401 instead of turning
  # a stale key into a burst of authentication failures that can lock out the
  # diagnostic workstation from HTTPS and SSH.
  posture_preflight_body="$(mktemp)"
  posture_preflight_meta="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
    -o "${posture_preflight_body}" -w '%{http_code}' \
    --header "@${POSTURE_API_HEADER_FILE}" \
    "${API_URL%/}/api/v2/system/version" 2>/dev/null || true)"
  if [[ "${posture_preflight_meta}" == "401" ]]; then
    log "posture_hostname endpoint=/api/v2/system/version http=401 ERROR class=authentication"
    jq -c '{code,status,response_id,message}' "${posture_preflight_body}" 2>/dev/null | tee -a "${REPORT}" || true
    warn "posture API key rejected; stopping authenticated API matrix to avoid triggering REST API Login Protection/sshguard"
    auth_lockout_risk=true
    api_failures=$((api_failures + 1))
  else
    for endpoint in "${posture_endpoints[@]}"; do
      probe_api "posture_hostname" "${API_URL}" false "${endpoint}" 200 "${POSTURE_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
    done
    probe_api "posture_hostname" "${API_URL}" false "/api/v2/diagnostics/table?id=snort2c" 403 "${POSTURE_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
    probe_api "posture_lan" "${LAN_API_URL}" true /api/v2/system/version 200 "${POSTURE_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
  fi
  rm -f "${posture_preflight_body}"
else
  log "WARN: PFSENSE_POSTURE_API_KEY unset: posture identity matrix not evaluated"
fi

if [[ "${auth_lockout_risk}" == true ]]; then
  log "WARN: security identity matrix skipped because an authentication lockout risk was detected"
elif [[ -n "${PFSENSE_SECURITY_API_KEY:-}" ]]; then
  SECURITY_API_HEADER_FILE="$(mktemp)"
  prepare_api_header "${PFSENSE_SECURITY_API_KEY}" "${SECURITY_API_HEADER_FILE}"
  probe_api "security_hostname" "${API_URL}" false "/api/v2/diagnostics/table?id=snort2c" 200 "${SECURITY_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
  probe_api "security_hostname" "${API_URL}" false /api/v2/status/services 403 "${SECURITY_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
  probe_api "security_lan" "${LAN_API_URL}" true "/api/v2/diagnostics/table?id=snort2c" 200 "${SECURITY_API_HEADER_FILE}" || api_failures=$((api_failures + 1))
else
  log "WARN: PFSENSE_SECURITY_API_KEY unset: security identity matrix not evaluated"
fi

if [[ "${MODE}" == "check" && "${ui_hostname_ok}" == false && "${ui_lan_ok}" == false ]]; then
  warn "both pfSense HTTPS vantage points are unreachable; skipping SSH deep diagnostics to avoid adding load during a possible appliance/network incident"
  fail "pfSense HTTPS is unreachable from both hostname and LAN vantage points; recover basic management reachability before deep diagnostics"
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
  -o ControlMaster=no
  -o ControlPath=none
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

section "REST API settings / service identities (redacted)"
run_optional pkg info -x 'pfSense-pkg-RESTAPI'
if [ -x /usr/local/bin/php ]; then
  /usr/local/bin/php <<'PHP' 2>&1 || true
<?php
require_once('/etc/inc/config.inc');
global $config;

$targets = ['fastapi_posture', 'fastapi_security'];
$expected = [
    'fastapi_posture' => [
        'api-v2-system-version-get',
        'api-v2-status-services-get',
        'api-v2-services-dns-resolver-settings-get',
        'api-v2-system-dns-get',
        'user-config-readonly',
    ],
    'fastapi_security' => [
        'api-v2-diagnostics-table-get',
        'user-config-readonly',
    ],
];

$api = [];
foreach (($config['installedpackages']['package'] ?? []) as $package) {
    if (($package['name'] ?? '') === 'RESTAPI') {
        $api = $package['conf'] ?? [];
        break;
    }
}
$authMethods = $api['auth_methods'] ?? [];
if (!is_array($authMethods)) {
    $authMethods = [$authMethods];
}
sort($authMethods);
printf(
    "restapi enabled=%s read_only=%s login_protection=%s auth_methods=%s\n",
    ($api['enabled'] ?? 'unknown'),
    ($api['read_only'] ?? 'unknown'),
    ($api['login_protection'] ?? 'unknown'),
    implode(',', $authMethods)
);

$users = $config['system']['user'] ?? [];
$groups = $config['system']['group'] ?? [];
foreach ($targets as $name) {
    $found = null;
    foreach ($users as $user) {
        if (($user['name'] ?? '') === $name) {
            $found = $user;
            break;
        }
    }
    if ($found === null) {
        printf("identity user=%s exists=no\n", $name);
        continue;
    }

    $privs = $found['priv'] ?? [];
    if (!is_array($privs)) {
        $privs = [$privs];
    }
    sort($privs);
    $missing = array_values(array_diff($expected[$name], $privs));
    $unexpected = array_values(array_diff($privs, $expected[$name]));
    $uid = (string)($found['uid'] ?? '');
    $admins = 'no';
    foreach ($groups as $group) {
        if (($group['name'] ?? '') !== 'admins') {
            continue;
        }
        $members = $group['member'] ?? [];
        if (!is_array($members)) {
            $members = [$members];
        }
        if ($uid !== '' && in_array($uid, array_map('strval', $members), true)) {
            $admins = 'yes';
        }
    }
    printf(
        "identity user=%s exists=yes disabled=%s admins=%s privileges=%s missing=%s unexpected=%s\n",
        $name,
        isset($found['disabled']) ? 'yes' : 'no',
        $admins,
        implode(',', $privs),
        $missing ? implode(',', $missing) : '<none>',
        $unexpected ? implode(',', $unexpected) : '<none>'
    );
}

$keys = $api['keys']['key'] ?? [];
if (!is_array($keys)) {
    $keys = [];
}
$keyCounts = array_fill_keys($targets, 0);
foreach ($keys as $key) {
    $username = (string)($key['username'] ?? '');
    if (!array_key_exists($username, $keyCounts)) {
        continue;
    }
    $keyCounts[$username]++;
    $descr = preg_replace('/\s+/', ' ', (string)($key['descr'] ?? ''));
    printf(
        "api_key user=%s length_bytes=%s hash_algo=%s descr=%s hash_present=%s\n",
        $username,
        (string)($key['length_bytes'] ?? 'unknown'),
        (string)($key['hash_algo'] ?? 'unknown'),
        $descr === '' ? '<empty>' : $descr,
        empty($key['hash']) ? 'no' : 'yes'
    );
}
foreach ($keyCounts as $username => $count) {
    printf("api_key_count user=%s count=%d\n", $username, $count);
}
PHP
else
  echo 'WARN: php CLI unavailable; REST API identity inventory skipped'
fi

section "Snort / pfBlockerNG / Login Protection / PF attribution"
pgrep -laf 'snort|pfblocker|pfb_|sshguard' 2>/dev/null || true
TABLES="$(pfctl -s Tables 2>/dev/null | egrep '^(snort2c|pfB_|pfb_|sshguard$)' || true)"
printf 'candidate_tables:\n%s\n' "${TABLES:-<none>}"
BLOCK_MATCH_COUNT=0
LOGIN_PROTECTION_MATCH_COUNT=0
for source in ${PROBE_SOURCES}; do
  for table in ${TABLES}; do
    if pfctl -t "${table}" -T show 2>/dev/null | awk -v ip="${source}" '$1 == ip {found=1} END {exit !found}'; then
      if [ "${table}" = sshguard ]; then
        LOGIN_PROTECTION_MATCH_COUNT=$((LOGIN_PROTECTION_MATCH_COUNT + 1))
        echo "LOGIN_PROTECTION_MATCH table=sshguard source=${source} exact=yes action=diagnose-only"
      else
        BLOCK_MATCH_COUNT=$((BLOCK_MATCH_COUNT + 1))
        echo "BLOCK_MATCH table=${table} source=${source} exact=yes"
      fi
      if [ "${MODE}" = apply ] && [ "${UNBLOCK_SOURCES}" = true ]; then
        case "${table}" in
          snort2c | pfB_* | pfb_*)
            echo "UNBLOCK_ACTION table=${table} source=${source}"
            pfctl -t "${table}" -T delete "${source}" 2>&1 || true
            ;;
          sshguard)
            echo "NO_UNBLOCK_ACTION table=sshguard source=${source} reason=login-protection-requires-separate-operator-review"
            ;;
        esac
      fi
    fi
  done
done
printf 'block_match_count=%s\n' "${BLOCK_MATCH_COUNT}"
printf 'login_protection_match_count=%s\n' "${LOGIN_PROTECTION_MATCH_COUNT}"

SNORT_CONF="$(find /usr/local/etc/snort -type f -path '*mvneta0.4090/snort.conf' 2>/dev/null | head -n 1)"
if [ -n "${SNORT_CONF}" ]; then
  HTTP_BLOCK="$(awk '
    /^preprocessor http_inspect_server/ {capture=1}
    capture {print}
    capture && $0 !~ /\\[[:space:]]*$/ {exit}
  ' "${SNORT_CONF}" 2>/dev/null)"
  HTTP_MEMCAP="$(grep -A12 'preprocessor http_inspect: global' "${SNORT_CONF}" 2>/dev/null | sed -n 's/.*memcap[[:space:]]\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  if printf '%s\n' "${HTTP_BLOCK}" | grep -Eq '(^|[^0-9])7000([^0-9]|$)'; then
    echo 'SNORT_HTTP_7000=present'
  else
    echo 'SNORT_HTTP_7000=absent'
  fi
  printf 'SNORT_HTTP_MEMCAP=%s\n' "${HTTP_MEMCAP:-unknown}"
else
  echo 'SNORT_HTTP_7000=unknown'
  echo 'SNORT_HTTP_MEMCAP=unknown'
fi

if [ "${BLOCK_MATCH_COUNT}" -gt 0 ]; then
  echo 'INGRESS_ATTRIBUTION=blocked_source_present'
elif [ -n "${SNORT_CONF}" ] && ! printf '%s\n' "${HTTP_BLOCK}" | grep -Eq '(^|[^0-9])7000([^0-9]|$)'; then
  echo 'INGRESS_ATTRIBUTION=snort2c_clear_http7000_absent'
else
  echo 'INGRESS_ATTRIBUTION=no_exact_block_match'
fi

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
