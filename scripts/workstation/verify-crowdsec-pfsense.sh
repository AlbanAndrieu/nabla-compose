#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="--accept"
EXPECTED_LAPI_URL="${CROWDSEC_EXPECTED_LAPI_URL:-http://172.17.0.24:8084}"
EXPECTED_LAPI_HOST="${CROWDSEC_EXPECTED_LAPI_HOST:-172.17.0.24}"
EXPECTED_LAPI_PORT="${CROWDSEC_EXPECTED_LAPI_PORT:-8084}"
LEGACY_LAPI_URL="${CROWDSEC_LEGACY_LAPI_URL:-http://172.17.0.1:8089}"
SSH_TARGET="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
SSH_PORT="${PFSENSE_SSH_PORT:-}"
REQUIRE_NONEMPTY=false

usage() {
  cat <<'EOF'
Usage: scripts/workstation/verify-crowdsec-pfsense.sh [--preflight|--accept] [--require-nonempty-table]

Read-only workstation-side pfSense validation for CrowdSec Small/remediation-only mode.

--preflight
  Validate the local Security Engine is stopped, the firewall bouncer is
  running, pfSense can reach the central TrueNAS LAPI, and PF tables exist.
  The legacy local LAPI URL is reported as a warning rather than a failure.

--accept
  Post-cutover acceptance (default). Requires the firewall bouncer api_url to
  point to the central TrueNAS LAPI.

--require-nonempty-table
  Require at least one entry across CrowdSec PF tables. Use this only when the
  TrueNAS diagnostic proves that the central LAPI has active ban decisions.

No pfSense configuration or service is modified.

Environment:
  PFSENSE_SSH_TARGET           SSH target (default: home.albandrieu.com)
  PFSENSE_SSH_PORT             Optional SSH port
  CROWDSEC_EXPECTED_LAPI_URL   Expected remote LAPI URL
  CROWDSEC_EXPECTED_LAPI_HOST  Expected LAPI host for TCP preflight
  CROWDSEC_EXPECTED_LAPI_PORT  Expected LAPI port for TCP preflight
  CROWDSEC_LEGACY_LAPI_URL     Known pre-cutover local LAPI URL
EOF
}

while (($# > 0)); do
  case "$1" in
    --preflight | --accept)
      MODE="$1"
      ;;
    --require-nonempty-table)
      REQUIRE_NONEMPTY=true
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

for command in ssh sed; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: required command missing: %s\n' "${command}" >&2
    exit 2
  }
done

ssh_args=(
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=1
)
if [[ -n "${SSH_PORT}" ]]; then
  ssh_args+=(-p "${SSH_PORT}")
fi

remote_output="$(
  ssh "${ssh_args[@]}" "${SSH_TARGET}" sh -s --     "${MODE}" "${EXPECTED_LAPI_URL}" "${EXPECTED_LAPI_HOST}"     "${EXPECTED_LAPI_PORT}" "${LEGACY_LAPI_URL}" "${REQUIRE_NONEMPTY}" <<'REMOTE'
set -eu

mode="$1"
expected_lapi="$2"
expected_host="$3"
expected_port="$4"
legacy_lapi="$5"
require_nonempty="$6"
failures=0
warnings=0

ok() { printf 'OK: %s\n' "$*"; }
warn() { warnings=$((warnings + 1)); printf 'WARNING: %s\n' "$*" >&2; }
error() { failures=$((failures + 1)); printf 'ERROR: %s\n' "$*" >&2; }

config='/usr/local/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml'

printf '==> pfSense CrowdSec Small runtime\n'
if pgrep -x crowdsec >/dev/null 2>&1; then
  error 'local CrowdSec Security Engine process is running; Small mode requires it stopped'
else
  ok 'local CrowdSec Security Engine process is absent'
fi

if service crowdsec_firewall onestatus >/dev/null 2>&1 &&
   pgrep -f '[c]rowdsec-firewall-bouncer' >/dev/null 2>&1; then
  ok 'CrowdSec firewall bouncer is running'
else
  error 'CrowdSec firewall bouncer is not running'
fi

printf '\n==> Central LAPI reachability\n'
if command -v nc >/dev/null 2>&1; then
  if nc -z -w 3 "${expected_host}" "${expected_port}" >/dev/null 2>&1; then
    ok "pfSense can reach central LAPI TCP ${expected_host}:${expected_port}"
  else
    error "pfSense cannot reach central LAPI TCP ${expected_host}:${expected_port}"
  fi
else
  warn 'nc is unavailable on pfSense; central LAPI TCP reachability was not tested'
fi

printf '\n==> Remote LAPI contract\n'
if [ ! -r "${config}" ]; then
  error "bouncer config is missing or unreadable: ${config}"
else
  api_url="$(
    awk '
      /^[[:space:]]*api_url[[:space:]]*:/ {
        line=$0
        sub(/^[^:]*:[[:space:]]*/, "", line)
        sub(/[[:space:]]+$/, "", line)
        gsub(/^["\\047]|["\\047]$/, "", line)
        print line
        exit
      }
    ' "${config}"
  )"
  case "${api_url}" in
    */) api_url="${api_url%/}" ;;
  esac
  expected="${expected_lapi%/}"
  legacy="${legacy_lapi%/}"
  printf 'crowdsec_bouncer_api_url=%s\n' "${api_url:-<missing>}"

  if [ "${api_url:-}" = "${expected}" ]; then
    ok "bouncer points to central LAPI ${expected}"
  elif [ "${mode}" = "--preflight" ] && [ "${api_url:-}" = "${legacy}" ]; then
    warn "bouncer still points to legacy local LAPI ${legacy}; expected before cutover"
  elif [ "${mode}" = "--preflight" ]; then
    warn "bouncer api_url is ${api_url:-<missing>}; cutover has not been accepted"
  else
    error "bouncer api_url is ${api_url:-<missing>}; expected ${expected}"
  fi
fi

printf '\n==> PF remediation tables\n'
total=0
for table in crowdsec_blacklists crowdsec6_blacklists; do
  table_output="$(mktemp)"
  if pfctl -t "${table}" -T show >"${table_output}" 2>/dev/null; then
    count="$(awk 'NF {count++} END {print count+0}' "${table_output}")"
    printf 'crowdsec_pf_table=%s entries=%s\n' "${table}" "${count}"
    total=$((total + count))
    ok "PF table ${table} exists"
  else
    error "PF table ${table} is missing or unreadable"
  fi
  rm -f "${table_output}"
done

if [ "${total}" -gt 0 ]; then
  ok "CrowdSec PF tables contain ${total} entrie(s)"
elif [ "${require_nonempty}" = true ]; then
  error 'CrowdSec PF tables are empty while non-empty remediation was required'
else
  warn 'CrowdSec PF tables are empty; acceptable only when the central LAPI has no active ban decisions'
fi

printf '\nCrowdSec pfSense Small summary: failures=%s warnings=%s table_entries=%s mode=%s\n' \
  "${failures}" "${warnings}" "${total}" "${mode}"
[ "${failures}" -eq 0 ]
REMOTE
)" || {
  status=$?
  printf '%s\n' "${remote_output:-}" |
    sed -E 's/(api_key[[:space:]]*:[[:space:]]*).*/\1<redacted>/I'
  exit "${status}"
}

printf '%s\n' "${remote_output}" |
  sed -E 's/(api_key[[:space:]]*:[[:space:]]*).*/\1<redacted>/I'
