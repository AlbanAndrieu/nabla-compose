#!/usr/bin/env bash
set -euo pipefail

TRUENAS_HOST="${TRUENAS_HOST:-172.17.0.24}"
PUBLIC_HOST="${PUBLIC_HOST:-sample.albandrieu.com}"
EXPECTED_PUBLIC_IP="${EXPECTED_PUBLIC_IP:-82.66.4.247}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://${TRUENAS_HOST}:8091/health}"
AUTOXPOSE_URL="${AUTOXPOSE_URL:-http://${TRUENAS_HOST}:4949}"
TRAEFIK_HOST="${TRAEFIK_HOST:-${TRUENAS_HOST}}"
TRAEFIK_PORT="${TRAEFIK_PORT:-443}"
ACME_FILE="${ACME_FILE:-/mnt/cpool/traefik/certs/acme.json}"
CERT_MIN_SECONDS="${CERT_MIN_SECONDS:-604800}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

printf '==> local FastAPI health\n'
curl --fail --silent --show-error --max-time 10 "${LOCAL_HEALTH_URL}" >/dev/null

printf '==> AutoXpose provider ownership\n'
status_json="$(curl --fail --silent --show-error --max-time 10 "${AUTOXPOSE_URL}/api/settings/status")"
python3 -c '
import json
import sys

status = json.load(sys.stdin)
dns = status.get("dns") or {}
proxy = status.get("proxy") or {}
if not dns.get("configured"):
    raise SystemExit("AutoXpose DNS provider is not configured")
if dns.get("provider") != "cloudflare":
    raise SystemExit(
        "AutoXpose DNS provider must be cloudflare, got {!r}".format(dns.get("provider"))
    )
if dns.get("domain") != "albandrieu.com":
    raise SystemExit(
        "AutoXpose DNS domain must be albandrieu.com, got {!r}".format(dns.get("domain"))
    )
if proxy.get("configured"):
    raise SystemExit(
        "AutoXpose proxy provider must stay disabled when Traefik owns routing; got {!r}".format(
            proxy.get("provider")
        )
    )
' <<<"${status_json}"

printf '==> public DNS\n'
resolved_ips="$(getent ahostsv4 "${PUBLIC_HOST}" | awk '{print $1}' | sort -u)"
grep -Fxq "${EXPECTED_PUBLIC_IP}" <<<"${resolved_ips}" || {
  printf 'Resolved IPv4 addresses:\n%s\n' "${resolved_ips}" >&2
  fail "${PUBLIC_HOST} does not resolve to expected public IP ${EXPECTED_PUBLIC_IP}"
}

check_certificate() {
  local connect_host="$1"
  local label="$2"
  local pem
  pem="$(timeout 15 openssl s_client \
    -connect "${connect_host}" \
    -servername "${PUBLIC_HOST}" \
    -verify_hostname "${PUBLIC_HOST}" \
    -verify_return_error </dev/null 2>/dev/null)" ||
    fail "${label} TLS handshake/hostname verification failed"

  printf '%s\n' "${pem}" |
    openssl x509 -noout -checkend "${CERT_MIN_SECONDS}" >/dev/null ||
    fail "${label} certificate expires in less than ${CERT_MIN_SECONDS} seconds"

  printf '%s\n' "${pem}" |
    openssl x509 -noout -subject -issuer -dates
}

printf '==> Traefik backend TLS certificate\n'
check_certificate "${TRAEFIK_HOST}:${TRAEFIK_PORT}" "Traefik"

printf '==> ACME store permissions\n'
if [[ -r "${ACME_FILE}" ]]; then
  [[ -s "${ACME_FILE}" ]] || fail "ACME store is empty: ${ACME_FILE}"
  mode="$(stat -c '%a' "${ACME_FILE}")"
  [[ "${mode}" == "600" ]] || fail "ACME store must have mode 600, got ${mode}"
  grep -Fq "${PUBLIC_HOST}" "${ACME_FILE}" ||
    fail "ACME store does not contain a certificate reference for ${PUBLIC_HOST}"
else
  printf 'SKIP: ACME store %s is not readable from this host (expected from a workstation)\n' "${ACME_FILE}"
fi

printf '==> public pfSense/HAProxy TLS certificate\n'
check_certificate "${PUBLIC_HOST}:443" "public ingress"

printf '==> public FastAPI health\n'
curl --fail --silent --show-error --max-time 15 "https://${PUBLIC_HOST}/health" >/dev/null

printf 'OK: %s is healthy through Cloudflare DNS -> pfSense HAProxy -> Traefik -> FastAPI Sample\n' "${PUBLIC_HOST}"
