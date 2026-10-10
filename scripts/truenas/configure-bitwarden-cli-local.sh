#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
PUBLIC_BASE="${NABLA_VAULTWARDEN_PUBLIC_BASE:-https://vaultwarden.albandrieu.com}"
LOCAL_ORIGIN="${NABLA_VAULTWARDEN_LOCAL_ORIGIN:-http://127.0.0.1:30032}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
usage: bash scripts/truenas/configure-bitwarden-cli-local.sh [--check|--apply]

Validate the local Vaultwarden origin, then configure the official Bitwarden
CLI with the canonical HTTPS Vaultwarden server.

The local HTTP origin is a health probe only. Bitwarden CLI 2026.x intentionally
rejects insecure API and identity URLs, including loopback URLs. Operational use
requires a working HTTPS client endpoint before login or secret materialization.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged operator, not root"

for command in bw curl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'Checking native Vaultwarden origin on %s/api/config...\n' "${LOCAL_ORIGIN}"
local_config="$(
  curl --fail --silent --show-error --max-time 5 "${LOCAL_ORIGIN}/api/config"
)" || fail "native Vaultwarden API is not reachable at ${LOCAL_ORIGIN}/api/config"

jq -e '
  type == "object" and
  (.environment | type == "object") and
  (.environment.api | type == "string") and
  (.environment.identity | type == "string")
' >/dev/null <<<"${local_config}" ||
  fail "native /api/config response is not a compatible Vaultwarden server config"

check_public_api() {
  local public_code
  public_code="$(
    curl --silent --show-error --max-time 10 \
      --output /dev/null --write-out '%{http_code}' \
      "${PUBLIC_BASE}/api/config" || true
  )"
  if [[ "${public_code}" != "200" ]]; then
    printf 'WARN: canonical HTTPS Vaultwarden client API returned HTTP %s: %s/api/config\n' \
      "${public_code:-000}" "${PUBLIC_BASE}" >&2
    return 1
  fi
  printf 'OK: canonical HTTPS Vaultwarden client API is reachable: %s/api/config\n' "${PUBLIC_BASE}"
}

if [[ "${MODE}" == "--check" ]]; then
  check_public_api ||
    fail "canonical HTTPS Vaultwarden ingress is incomplete; fix /api and /identity routing before CLI login"
  printf 'OK: local origin and HTTPS client endpoint are ready.\n'
  exit 0
fi

configured_before="$(bw config server 2>/dev/null | tr -d '\r\n' || true)"
status="$(
  bw status 2>/dev/null | jq -r '.status // "unknown"' 2>/dev/null || printf 'unknown'
)"

case "${status}" in
  unauthenticated)
    ;;
  locked | unlocked)
    fail "Bitwarden CLI status is ${status}; run 'bw logout' before changing server configuration"
    ;;
  unknown)
    printf 'WARN: Bitwarden CLI status is unavailable before endpoint reset; base=%s. Resetting all per-service endpoints because --apply was explicitly requested.\n' \
      "${configured_before:-<unset>}" >&2
    ;;
  *)
    fail "unexpected Bitwarden CLI status: ${status}"
    ;;
esac

# Bitwarden CLI supports per-service endpoint overrides. Configure the complete
# set in one command so stale api/identity loopback overrides cannot survive
# even when `bw config server` prints the canonical base URL.
bw config server \
  --web-vault "${PUBLIC_BASE}" \
  --api "${PUBLIC_BASE}/api" \
  --identity "${PUBLIC_BASE}/identity" \
  --icons "${PUBLIC_BASE}/icons" \
  --notifications "${PUBLIC_BASE}/notifications" \
  --events "${PUBLIC_BASE}/events"

printf 'OK: Bitwarden CLI per-service endpoints reset to canonical HTTPS origin %s\n' "${PUBLIC_BASE}"

check_public_api ||
  fail "CLI overrides are now HTTPS-only, but canonical Vaultwarden ingress still returns a non-200 /api/config; fix the tunnel/origin route before login"
