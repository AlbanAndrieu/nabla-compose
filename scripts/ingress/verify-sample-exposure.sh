#!/usr/bin/env bash
set -euo pipefail

TRUENAS_HOST="${TRUENAS_HOST:-172.17.0.24}"
PUBLIC_HOST="${PUBLIC_HOST:-sample.albandrieu.com}"
INTERNAL_HOST="${INTERNAL_HOST:-sample.int.albandrieu.com}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://${TRUENAS_HOST}:8091/health}"
TRAEFIK_HOST="${TRAEFIK_HOST:-${TRUENAS_HOST}}"
TRAEFIK_PORT="${TRAEFIK_PORT:-443}"
ACME_FILE="${ACME_FILE:-/mnt/cpool/traefik/certs/acme.json}"
CERT_MIN_SECONDS="${CERT_MIN_SECONDS:-604800}"
PFSENSE_DNS="${PFSENSE_DNS:-172.17.0.1}"
PIHOLE_DNS="${PIHOLE_DNS:-172.17.0.24}"

warnings=0

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

resolve_a_with_server() {
  local server="$1"
  local hostname="$2"

  command -v dig >/dev/null 2>&1 ||
    fail "dig is required for authoritative/split-DNS verification"

  dig +time=3 +tries=1 +short @"${server}" "${hostname}" A 2>/dev/null |
    awk '/^[0-9]+([.][0-9]+){3}$/ { print }' |
    sort -u
}

require_truenas_answer() {
  local label="$1"
  local answers="$2"

  [[ -n "${answers}" ]] || fail "${label}: ${INTERNAL_HOST} returned no IPv4 answer"
  if ! grep -Fxq "${TRUENAS_HOST}" <<<"${answers}"; then
    printf '%s resolved IPv4 addresses:\n%s\n' "${label}" "${answers}" >&2
    fail "${label}: ${INTERNAL_HOST} does not resolve to TrueNAS ${TRUENAS_HOST}"
  fi
}

check_certificate() {
  local connect_host="$1"
  local server_name="$2"
  local label="$3"
  local pem

  pem="$(timeout 15 openssl s_client \
    -connect "${connect_host}" \
    -servername "${server_name}" \
    -verify_hostname "${server_name}" \
    -verify_return_error </dev/null 2>/dev/null)" ||
    fail "${label} TLS handshake/hostname verification failed"

  printf '%s\n' "${pem}" |
    openssl x509 -noout -checkend "${CERT_MIN_SECONDS}" >/dev/null ||
    fail "${label} certificate expires in less than ${CERT_MIN_SECONDS} seconds"

  printf '%s\n' "${pem}" |
    openssl x509 -noout -subject -issuer -dates
}

printf '==> TrueNAS FastAPI health\n'
curl --fail --silent --show-error --max-time 10 "${LOCAL_HEALTH_URL}" >/dev/null

printf '==> internal Pi-hole DNS (authoritative private record)\n'
pihole_ips="$(resolve_a_with_server "${PIHOLE_DNS}" "${INTERNAL_HOST}")"
require_truenas_answer "Pi-hole authoritative DNS" "${pihole_ips}"

printf '==> pfSense/Unbound split DNS\n'
pfsense_ips="$(resolve_a_with_server "${PFSENSE_DNS}" "${INTERNAL_HOST}")"
require_truenas_answer "pfSense/Unbound split DNS" "${pfsense_ips}"

printf '==> system resolver view (non-blocking warning; prefer pfSense/Unbound)\n'
system_ips="$(getent ahostsv4 "${INTERNAL_HOST}" 2>/dev/null | awk '{print $1}' | sort -u || true)"
if [[ -n "${system_ips}" ]] && grep -Fxq "${TRUENAS_HOST}" <<<"${system_ips}"; then
  printf 'OK: system resolver view resolves %s to TrueNAS %s\n' "${INTERNAL_HOST}" "${TRUENAS_HOST}"
else
  printf 'WARNING: system resolver view differs from private DNS; prefer pfSense/Unbound for clients (non-blocking warning)\n' >&2
  warnings=$((warnings + 1))
fi

printf '==> internal Traefik TLS certificate\n'
check_certificate "${TRAEFIK_HOST}:${TRAEFIK_PORT}" "${INTERNAL_HOST}" "Traefik internal ingress"

printf '==> internal FastAPI through Traefik\n'
curl --fail --silent --show-error --max-time 15 \
  --resolve "${INTERNAL_HOST}:443:${TRAEFIK_HOST}" \
  "https://${INTERNAL_HOST}/health" >/dev/null

printf '==> Traefik ACME store permissions\n'
if [[ -r "${ACME_FILE}" ]]; then
  [[ -s "${ACME_FILE}" ]] || fail "ACME store is empty: ${ACME_FILE}"
  mode="$(stat -c '%a' "${ACME_FILE}")"
  [[ "${mode}" == "600" ]] || fail "ACME store must have mode 600, got ${mode}"
else
  printf 'SKIP: ACME store %s is not readable from this host (expected from a workstation)\n' "${ACME_FILE}"
fi

printf '==> public Cloudflare DNS\n'
public_ips="$(getent ahostsv4 "${PUBLIC_HOST}" 2>/dev/null | awk '{print $1}' | sort -u || true)"
[[ -n "${public_ips}" ]] || fail "${PUBLIC_HOST} does not resolve"
printf '%s\n' "${public_ips}"

printf '==> public Cloudflare edge TLS certificate\n'
check_certificate "${PUBLIC_HOST}:443" "${PUBLIC_HOST}" "Cloudflare edge"

printf '==> public Cloudflare Access / Tunnel\n'
if [[ -n "${CF_ACCESS_CLIENT_ID:-}" || -n "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
  [[ -n "${CF_ACCESS_CLIENT_ID:-}" && -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] ||
    fail "CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET must be provided together"

  token_headers="$(mktemp)"
  token_body="$(mktemp)"
  trap 'rm -f "${token_headers}" "${token_body}"' EXIT

  token_status="$(curl --silent --show-error --max-time 20 \
    --output "${token_body}" --dump-header "${token_headers}" \
    --write-out '%{http_code}' \
    -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
    -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
    "https://${PUBLIC_HOST}/health")"

  token_content_type="$(
    awk 'BEGIN { IGNORECASE=1 } /^content-type:/ {
      sub(/^[^:]*:[[:space:]]*/, "")
      sub(/\r$/, "")
      print
      exit
    }' "${token_headers}"
  )"
  printf 'Cloudflare token response: HTTP %s · Content-Type %s\n' \
    "${token_status}" "${token_content_type:-unknown}"

  if [[ "${token_status}" != "200" ]]; then
    if grep -Eiq 'cloudflare-access|cloudflareaccess\.com|www-authenticate:.*Cloudflare-Access' "${token_headers}"; then
      fail "service token was not accepted by Cloudflare Access; verify a Service Auth policy includes this token"
    fi
    fail "authenticated public health returned HTTP ${token_status}; inspect the Tunnel route/origin"
  fi

  if [[ "${token_content_type}" != application/json* ]]; then
    printf 'Response preview: ' >&2
    head -c 160 "${token_body}" | tr '\n' ' ' >&2
    printf '\n' >&2
    fail "authenticated public health returned HTTP 200 but not JSON"
  fi

  python3 -m json.tool "${token_body}" >/dev/null ||
    fail "authenticated public health returned invalid JSON"

  printf 'OK: authenticated Cloudflare Access request reached FastAPI Sample\n'
else
  headers="$(mktemp)"
  trap 'rm -f "${headers}"' EXIT

  status="$(curl --silent --show-error --max-time 20 \
    --output /dev/null --dump-header "${headers}" \
    --write-out '%{http_code}' "https://${PUBLIC_HOST}/health")"

  if [[ "${status}" != "302" && "${status}" != "401" && "${status}" != "403" ]]; then
    fail "expected a Cloudflare Access challenge without credentials, got HTTP ${status}"
  fi

  if ! grep -Eiq 'cloudflare-access|cloudflareaccess\.com|www-authenticate:.*Cloudflare-Access' "${headers}"; then
    cat "${headers}" >&2
    fail "public response does not contain Cloudflare Access challenge evidence"
  fi

  printf 'OK: Cloudflare Access is enforcing authentication (HTTP %s)\n' "${status}"
  printf 'INFO: set CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET to prove the full Tunnel origin path\n'
fi

if ((warnings > 0)); then
  printf 'WARNING: acceptance completed with %d non-blocking warning(s)\n' "${warnings}" >&2
fi

printf 'OK: internal Pi-hole -> pfSense/Unbound -> Traefik and public Cloudflare Access/Tunnel contracts are consistent for FastAPI Sample\n'
