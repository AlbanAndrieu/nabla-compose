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
rejects insecure API and identity URLs, including loopback URLs.
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

public_code="$(
  curl --silent --show-error --max-time 10 \
    --output /dev/null --write-out '%{http_code}' \
    "${PUBLIC_BASE}/api/config" || true
)"
if [[ "${public_code}" != "200" ]]; then
  printf 'WARN: canonical HTTPS Vaultwarden client API returned HTTP %s: %s/api/config\n' \
    "${public_code:-000}" "${PUBLIC_BASE}" >&2
  fail "official Bitwarden CLI requires a working HTTPS client endpoint; do not use the HTTP loopback origin as an API override"
fi

printf 'OK: canonical HTTPS Vaultwarden client API is reachable: %s/api/config\n' "${PUBLIC_BASE}"

if [[ "${MODE}" == "--check" ]]; then
  printf 'OK: local origin and HTTPS client endpoint are ready.\n'
  exit 0
fi

status="$(
  bw status 2>/dev/null | jq -r '.status // "unknown"' 2>/dev/null || printf 'unknown'
)"
if [[ "${status}" != "unauthenticated" ]]; then
  fail "Bitwarden CLI status is ${status}; run 'bw logout' before changing server configuration"
fi

# A plain server assignment clears stale per-service overrides. Never point the
# official CLI at LOCAL_ORIGIN because it is intentionally HTTP-only.
bw config server "${PUBLIC_BASE}"

configured_base="$(bw config server | tr -d '\r\n')"
[[ "${configured_base%/}" == "${PUBLIC_BASE%/}" ]] ||
  fail "Bitwarden CLI base mismatch after configuration: ${configured_base:-<unset>}"

printf 'OK: Bitwarden CLI configured for canonical HTTPS server %s\n' "${PUBLIC_BASE}"
