#!/usr/bin/env bash
# Read-only probe of an Overkiz-based io-homecontrol gateway: Somfy TaHoma or
# Connexoon, or an operator-branded box such as the Flexom (Ubiant, Bouygues
# Immobilier) gateway in the electrical panel. It answers one question: can
# Home Assistant drive it locally (Overkiz local API, "developer mode"), or is
# it a cloud-only box to replace?
#
#   bash scripts/truenas/diagnose-homeassistant-overkiz.sh --host <ip-or-name>
#   bash scripts/truenas/diagnose-homeassistant-overkiz.sh --discover
#
# Without credentials: mDNS discovery (same network segment only), TCP
# reachability, TLS certificate identity and the HTTP status of the local API
# version endpoint. Every local API call requires a token, so 401/403 proves
# that the API listens. Without the Overkiz root CA, that single
# unauthenticated status probe skips certificate verification: nothing secret
# is sent and only the status code is read.
#
# Optional inventory: root:root 600 env file ${NABLA_OVERKIZ_SECRETS_FILE}
# (default /mnt/cpool/secrets/runtime/homeassistant/overkiz.env) holding
# OVERKIZ_TOKEN, plus NABLA_OVERKIZ_CA_FILE (Overkiz root CA whose fingerprint
# the operator checked) and NABLA_OVERKIZ_TLS_NAME (certificate name, e.g.
# gateway-XXXX-XXXX-XXXX.local). The token is only sent over verified TLS.
# The inventory prints device counts by protocol and type, never labels or
# device URLs. GET requests only: nothing changes on the gateway.
set -euo pipefail

usage() {
  echo 'Usage: bash scripts/truenas/diagnose-homeassistant-overkiz.sh [--check] (--host <ip-or-name> | --discover)'
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
# shellcheck source=../lib/probe.sh
source "${SCRIPT_DIR}/../lib/probe.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

HOST="${NABLA_OVERKIZ_HOST:-}"
DISCOVER=0
while (($# > 0)); do
  case "$1" in
  --check) shift ;;
  --discover)
    DISCOVER=1
    shift
    ;;
  --host)
    [[ $# -ge 2 ]] || {
      usage >&2
      exit 2
    }
    HOST="$2"
    shift 2
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
  esac
done
[[ -n "${HOST}" || "${DISCOVER}" == 1 ]] || {
  usage >&2
  exit 2
}
[[ -z "${HOST}" || "${HOST}" =~ ^[A-Za-z0-9.-]+$ ]] || {
  echo 'ERROR invalid --host' >&2
  exit 2
}
for cmd in curl openssl jq timeout; do
  command -v "${cmd}" >/dev/null 2>&1 || {
    printf 'ERROR missing=%s\n' "${cmd}" >&2
    exit 2
  }
done
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

SECRETS_FILE="${NABLA_OVERKIZ_SECRETS_FILE:-/mnt/cpool/secrets/runtime/homeassistant/overkiz.env}"
CA_FILE="${NABLA_OVERKIZ_CA_FILE:-}"
TLS_NAME="${NABLA_OVERKIZ_TLS_NAME:-}"
API_PATH=/enduser-mobile-web/1/enduserAPI
declare -A OPEN=()
OVERKIZ_HW=0
LOCAL_API=0

# Gateway PINs (XXXX-XXXX-XXXX) identify the box in Overkiz device URLs: keep
# the first group only.
mask_pin() { sed -E 's/([0-9]{4})-[0-9]{4}-[0-9]{4}/\1-XXXX-XXXX/g'; }

diag_section '1/4' 'Discovery (mDNS, same network segment only)'
if ((DISCOVER == 0)) && [[ -n "${HOST}" ]]; then
  diag_info 'Discovery skipped: --host given (add --discover to browse mDNS too)'
elif command -v avahi-browse >/dev/null 2>&1; then
  found=0
  for service in _kizboxdev._tcp _kizbox._tcp; do
    results="$(timeout 12 avahi-browse --resolve --parsable --terminate "${service}" 2>/dev/null | grep '^=' || true)"
    while IFS=';' read -r _ _ _ _ _ _ hostname address port txt; do
      [[ -n "${address}" ]] || continue
      found=1
      api="$(grep -oE 'api_version=[^"]*' <<<"${txt}" || true)"
      printf 'mdns service=%s host=%s address=%s port=%s %s\n' \
        "${service}" "$(mask_pin <<<"${hostname}")" "${address}" "${port}" "${api}"
      if [[ -z "${HOST}" && "${address}" =~ ^[0-9.]+$ ]]; then HOST="${address}"; fi
    done <<<"${results}"
  done
  ((found)) || diag_info 'No Overkiz announcement here: mDNS does not cross pfSense from LAN to OPT; check the DHCP leases on OPT'
else
  diag_info 'avahi-browse not installed: discovery skipped (use --host with the DHCP lease address)'
fi
if [[ -z "${HOST}" ]]; then
  diag_fail 'No gateway address: pass --host <ip>'
  diag_summary
  exit 1
fi
printf 'target=%s\n' "${HOST}"

diag_section '2/4' 'TCP reachability'
for port in 80 443 8443; do
  if probe_tcp_success "${HOST}" "${port}" 3; then
    OPEN[${port}]=1
    printf 'tcp=%s open\n' "${port}"
  else
    printf 'tcp=%s closed-or-filtered\n' "${port}"
  fi
done
if ((${#OPEN[@]} == 0)); then
  diag_fail 'Gateway unreachable on 80/443/8443: wrong address, powered off, or no pfSense rule from this host to OPT'
fi

diag_section '3/4' 'TLS identity (subject, issuer, expiry; PIN masked)'
for port in 8443 443; do
  [[ "${OPEN[${port}]:-0}" == 1 ]] || continue
  sni=()
  [[ "${HOST}" =~ [A-Za-z] ]] && sni=(-servername "${HOST}")
  cert="$(timeout 8 openssl s_client -connect "${HOST}:${port}" "${sni[@]}" </dev/null 2>/dev/null |
    openssl x509 2>/dev/null || true)"
  if [[ -z "${cert}" ]]; then
    diag_warn "Port ${port}: no TLS certificate presented"
    continue
  fi
  identity="$(openssl x509 -noout -subject -issuer -enddate -nameopt RFC2253 <<<"${cert}" | mask_pin | paste -sd ' ' -)"
  printf 'tls_port=%s %s\n' "${port}" "${identity}"
  if grep -qi overkiz <<<"${identity}"; then
    OVERKIZ_HW=1
    diag_ok "Port ${port}: certificate issued by an Overkiz authority (Overkiz hardware)"
  fi
done

diag_section '4/4' 'Overkiz local API (developer mode)'
token=''
if [[ -e "${SECRETS_FILE}" ]]; then
  if secrets_assert_file "${SECRETS_FILE}" OVERKIZ_TOKEN; then
    token="$(secrets_get_value "${SECRETS_FILE}" OVERKIZ_TOKEN || true)"
  else
    diag_fail "${SECRETS_FILE} is unsafe or malformed (expected root:root 600 with OVERKIZ_TOKEN=)"
  fi
fi
verified=0
if [[ -n "${CA_FILE}${TLS_NAME}" ]]; then
  if [[ -r "${CA_FILE}" && "${TLS_NAME}" =~ ^[A-Za-z0-9.-]+$ ]]; then
    verified=1
  else
    diag_fail 'Verified TLS needs both a readable NABLA_OVERKIZ_CA_FILE and a valid NABLA_OVERKIZ_TLS_NAME'
  fi
fi
if [[ "${OPEN[8443]:-0}" == 1 ]]; then
  if ((verified)); then
    tls=(--cacert "${CA_FILE}" --resolve "${TLS_NAME}:8443:${HOST}")
    base="https://${TLS_NAME}:8443${API_PATH}"
  else
    tls=(--insecure)
    base="https://${HOST}:8443${API_PATH}"
  fi
  code="$(curl --silent --output /dev/null --write-out '%{http_code}' --connect-timeout 3 --max-time 8 \
    "${tls[@]}" "${base}/apiVersion" 2>/dev/null || true)"
  printf 'local_api_probe http=%s tls_verified=%s\n' "${code:-000}" "$([[ ${verified} == 1 ]] && echo yes || echo no)"
  case "${code}" in
  200 | 401 | 403)
    LOCAL_API=1
    diag_ok 'Overkiz local API listens (developer mode enabled)'
    ;;
  404) diag_warn 'HTTPS on 8443 without the local API path' ;;
  *) diag_warn "Local API probe returned HTTP ${code:-000}" ;;
  esac
  if ((LOCAL_API)) && [[ -n "${token}" ]]; then
    if ((verified)); then
      if devices="$(curl --fail --silent --show-error --connect-timeout 3 --max-time 15 "${tls[@]}" \
        --header @<(secrets_curl_headers Authorization "Bearer ${token}") "${base}/setup/devices")"; then
        jq -r 'map(.deviceURL // "unknown" | split(":")[0]) | group_by(.) | map("protocol=\(.[0]) devices=\(length)") | .[]' <<<"${devices}"
        jq -r 'map(.controllableName // "unknown") | group_by(.) | map("type=\(.[0]) devices=\(length)") | .[]' <<<"${devices}"
        diag_ok 'Token accepted: device inventory read locally'
      else
        diag_fail 'Token rejected or inventory unreadable'
      fi
    else
      diag_warn 'Token not sent: set NABLA_OVERKIZ_CA_FILE and NABLA_OVERKIZ_TLS_NAME for verified TLS first'
    fi
  fi
elif ((${#OPEN[@]} > 0)); then
  diag_info 'Port 8443 closed: the local API (developer mode) is not enabled on this gateway'
else
  diag_unknown 'Local API not checked: gateway unreachable'
fi

diag_section '' 'Verdict'
if ((LOCAL_API)); then
  diag_info 'Local path possible: Home Assistant Overkiz integration in local API mode with a token generated in the gateway operator app'
elif ((OVERKIZ_HW)); then
  diag_warn 'Overkiz hardware without local API: cloud-only through its operator. Independent path: an io gateway with a local API, then re-pair the motors'
else
  diag_unknown 'Not identified as an Overkiz gateway at this address'
fi

diag_summary
((DIAG_FAILURES == 0))
