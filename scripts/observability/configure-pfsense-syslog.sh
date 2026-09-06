#!/usr/bin/env bash
set -euo pipefail

mode="check"
case "${1:-}" in
  "" | --check) mode="check" ;;
  --plan) mode="plan" ;;
  --apply) mode="apply" ;;
  *)
    echo "usage: $0 [--check|--plan|--apply]" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

PFSENSE_API_URL="${PFSENSE_API_URL:-https://172.17.0.1:10443}"
PFSENSE_SYSLOG_TARGET="${PFSENSE_SYSLOG_TARGET:-172.17.0.24:1514}"
PFSENSE_SYSLOG_SOURCE_INTERFACE="${PFSENSE_SYSLOG_SOURCE_INTERFACE:-}"
PFSENSE_API_INSECURE_SKIP_VERIFY="${PFSENSE_API_INSECURE_SKIP_VERIFY:-false}"
PFSENSE_RESTAPI_MIN_VERSION="v2.9.0"

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

version_at_least() {
  local current="$1"
  local required="$2"
  local current_major current_minor current_patch
  local required_major required_minor required_patch

  if [[ ! "${current}" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    return 2
  fi
  current_major="${BASH_REMATCH[1]}"
  current_minor="${BASH_REMATCH[2]}"
  current_patch="${BASH_REMATCH[3]}"

  if [[ ! "${required}" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    return 2
  fi
  required_major="${BASH_REMATCH[1]}"
  required_minor="${BASH_REMATCH[2]}"
  required_patch="${BASH_REMATCH[3]}"

  ((current_major > required_major)) && return 0
  ((current_major < required_major)) && return 1
  ((current_minor > required_minor)) && return 0
  ((current_minor < required_minor)) && return 1
  ((current_patch >= required_patch))
}

for command in curl jq mktemp; do
  if command -v "${command}" >/dev/null 2>&1; then
    ok "command available: ${command}"
  else
    fail "missing command: ${command}"
  fi
done

if [[ -z "${PFSENSE_OBSERVABILITY_API_KEY:-}" ]]; then
  fail "PFSENSE_OBSERVABILITY_API_KEY is required; use a dedicated local operator key with GET restapi/version and GET/PATCH status/logs/settings only"
fi

if ((errors > 0)); then
  exit 1
fi

if [[ "${mode}" == "apply" ]]; then
  printf '\n🔒 Running strict observability preflight before any pfSense mutation\n'
  "${SCRIPT_DIR}/verify-stack.sh" --strict
else
  printf '\n🔎 Running read-only observability preflight\n'
  "${SCRIPT_DIR}/verify-stack.sh"
fi

curl_common=(
  --silent
  --show-error
  --connect-timeout 5
  --max-time 20
  --header "Accept: application/json"
  --header "Content-Type: application/json"
  --header "X-API-Key: ${PFSENSE_OBSERVABILITY_API_KEY}"
)

if [[ -n "${PFSENSE_API_CA_BUNDLE:-}" ]]; then
  curl_common+=(--cacert "${PFSENSE_API_CA_BUNDLE}")
elif [[ "${PFSENSE_API_INSECURE_SKIP_VERIFY}" == "true" ]]; then
  warn "pfSense API TLS verification is disabled explicitly"
  curl_common+=(--insecure)
elif [[ "${PFSENSE_API_INSECURE_SKIP_VERIFY}" != "false" ]]; then
  fail "PFSENSE_API_INSECURE_SKIP_VERIFY must be true or false"
fi

if ((errors > 0)); then
  exit 1
fi

version_url="${PFSENSE_API_URL%/}/api/v2/system/restapi/version"
version_file="${tmp_dir}/restapi-version.json"
status="$(
  curl "${curl_common[@]}" \
    --output "${version_file}" \
    --write-out '%{http_code}' \
    "${version_url}" || true
)"

if [[ "${status}" != "200" ]]; then
  fail "unable to read pfREST version (HTTP ${status:-none})"
  exit 1
fi
if ! jq -e '.data.current_version | type == "string"' "${version_file}" >/dev/null 2>&1; then
  fail "pfREST version response does not contain data.current_version"
  exit 1
fi

current_restapi_version="$(jq -r '.data.current_version' "${version_file}")"
if version_at_least "${current_restapi_version}" "${PFSENSE_RESTAPI_MIN_VERSION}"; then
  ok "pfREST version ${current_restapi_version} satisfies security floor ${PFSENSE_RESTAPI_MIN_VERSION}"
else
  fail "pfREST ${current_restapi_version} is below required security floor ${PFSENSE_RESTAPI_MIN_VERSION}; upgrade pfREST before granting the PATCH window"
  exit 1
fi

settings_url="${PFSENSE_API_URL%/}/api/v2/status/logs/settings"
current_file="${tmp_dir}/current.json"
status="$(curl "${curl_common[@]}"   --output "${current_file}" --write-out '%{http_code}'   "${settings_url}" || true)"

if [[ "${status}" != "200" ]] || ! jq -e '.data | type == "object"' "${current_file}" >/dev/null 2>&1; then
  fail "unable to read pfSense log settings (HTTP ${status:-none})"
  exit 1
fi
ok "pfSense log settings API is readable"

target_field=""
first_empty=""
for field in remoteserver remoteserver2 remoteserver3; do
  value="$(jq -r --arg field "${field}" '.data[$field] // ""' "${current_file}")"
  if [[ "${value}" == "${PFSENSE_SYSLOG_TARGET}" ]]; then
    target_field="${field}"
    break
  fi
  if [[ -z "${value}" && -z "${first_empty}" ]]; then
    first_empty="${field}"
  fi
done

if [[ -z "${target_field}" ]]; then
  target_field="${first_empty}"
fi
if [[ -z "${target_field}" ]]; then
  fail "all three pfSense remote syslog slots are already occupied; no existing destination was overwritten"
  exit 1
fi

desired="$(jq -n   --arg target_field "${target_field}"   --arg target "${PFSENSE_SYSLOG_TARGET}"   '{
    format: "rfc5424",
    enableremotelogging: true,
    ipprotocol: "ipv4",
    logall: false,
    filter: true,
    dhcp: true,
    auth: true,
    vpn: true,
    dpinger: true,
    system: true,
    resolver: true
  } + {($target_field): $target}')"

if [[ -n "${PFSENSE_SYSLOG_SOURCE_INTERFACE}" ]]; then
  desired="$(jq     --arg source "${PFSENSE_SYSLOG_SOURCE_INTERFACE}"     '. + {sourceip: $source}' <<<"${desired}")"
fi

printf '\n🧭 Desired pfSense remote logging contract\n'
jq . <<<"${desired}"

if [[ "${mode}" == "check" ]]; then
  ok "read-only pfSense inspection completed; no PATCH request was sent"
  printf '\nCurrent configuration was read successfully. Re-run with --plan to validate the desired PATCH through pfREST dry-run.\n'
  exit 0
fi

request_file="${tmp_dir}/request.json"
response_file="${tmp_dir}/response.json"
if [[ "${mode}" == "plan" ]]; then
  jq '. + {dry_run: true}' <<<"${desired}" >"${request_file}"
else
  printf '%s\n' "${desired}" >"${request_file}"
fi

status="$(curl "${curl_common[@]}"   --request PATCH   --data-binary "@${request_file}"   --output "${response_file}" --write-out '%{http_code}'   "${settings_url}" || true)"

if [[ ! "${status}" =~ ^2[0-9][0-9]$ ]]; then
  fail "pfSense log settings ${mode} request failed (HTTP ${status:-none})"
  if jq -e . "${response_file}" >/dev/null 2>&1; then
    jq '{code, status, response_id, message}' "${response_file}" >&2 || true
  fi
  exit 1
fi

if [[ "${mode}" == "plan" ]]; then
  ok "pfSense accepted the remote logging configuration as a dry-run"
  printf '\nNo pfSense configuration was changed. Re-run with --apply after reviewing the payload.\n'
  exit 0
fi

ok "pfSense accepted the remote logging configuration"

sleep 3
verify_file="${tmp_dir}/verify.json"
status="$(curl "${curl_common[@]}"   --output "${verify_file}" --write-out '%{http_code}'   "${settings_url}" || true)"

if [[ "${status}" != "200" ]]; then
  fail "unable to read pfSense settings after apply (HTTP ${status:-none})"
  exit 1
fi

expected_checks=(
  'format=="rfc5424"'
  'enableremotelogging==true'
  'ipprotocol=="ipv4"'
  'logall==false'
  'filter==true'
  'dhcp==true'
  'auth==true'
  'vpn==true'
  'dpinger==true'
  'system==true'
  'resolver==true'
)
for check in "${expected_checks[@]}"; do
  field="${check%%==*}"
  expected="${check#*==}"
  if jq -e --arg field "${field}" --argjson expected "${expected}"     '.data[$field] == $expected' "${verify_file}" >/dev/null 2>&1; then
    ok "pfSense setting verified: ${field}"
  else
    fail "pfSense setting verification failed: ${field}"
  fi
done

if jq -e --arg field "${target_field}" --arg target "${PFSENSE_SYSLOG_TARGET}"   '.data[$field] == $target' "${verify_file}" >/dev/null 2>&1; then
  ok "pfSense remote syslog destination verified in ${target_field}"
else
  fail "pfSense remote syslog destination verification failed"
fi

if [[ -n "${PFSENSE_SYSLOG_SOURCE_INTERFACE}" ]]; then
  if jq -e --arg source "${PFSENSE_SYSLOG_SOURCE_INTERFACE}"     '.data.sourceip == $source' "${verify_file}" >/dev/null 2>&1; then
    ok "pfSense remote syslog source interface verified"
  else
    fail "pfSense remote syslog source interface verification failed"
  fi
fi

if ((errors > 0)); then
  printf '\n❌ pfSense configuration applied but post-apply verification found %d error(s).\n' "${errors}" >&2
  exit 1
fi

printf '\n🧪 Verifying the log transport\n'
"${SCRIPT_DIR}/verify-pfsense-syslog.sh" --synthetic-only
if "${SCRIPT_DIR}/verify-pfsense-syslog.sh" --live-only; then
  ok "real pfSense records are already visible in Loki"
else
  warn "pfSense is configured, but no real pfSense record was observed yet; generate normal firewall/system activity and rerun the live check"
fi

printf '\n✅ pfSense RFC5424 remote logging configuration is applied and the homelab receiver path is healthy.\n'
