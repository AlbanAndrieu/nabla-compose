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

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
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

printf '==> internal Pi-hole DNS\n'
internal_ips="$(getent ahostsv4 "${INTERNAL_HOST}" 2>/dev/null | awk '{print $1}' | sort -u || true)"
[[ -n "${internal_ips}" ]] || fail "${INTERNAL_HOST} does not resolve"
grep -Fxq "${TRUENAS_HOST}" <<<"${internal_ips}" || {
  printf 'Resolved IPv4 addresses:\n%s\n' "${internal_ips}" >&2
  fail "${INTERNAL_HOST} does not resolve to TrueNAS ${TRUENAS_HOST}"
}

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

  curl --fail --silent --show-error --max-time 20 \
    -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
    -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
    "https://${PUBLIC_HOST}/health" >/dev/null

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

printf 'OK: internal Pi-hole -> Traefik and public Cloudflare Access/Tunnel contracts are consistent for FastAPI Sample\n'
