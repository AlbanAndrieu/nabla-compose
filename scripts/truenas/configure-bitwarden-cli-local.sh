#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
PUBLIC_BASE="${NABLA_VAULTWARDEN_PUBLIC_BASE:-https://vaultwarden.albandrieu.com}"
LOCAL_BASE="${NABLA_VAULTWARDEN_LOCAL_BASE:-http://127.0.0.1:30032}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
usage: bash scripts/truenas/configure-bitwarden-cli-local.sh [--check|--apply]

Configure the official Bitwarden CLI on the TrueNAS operator account so API
and identity traffic uses the local Vaultwarden listener while the canonical
public URL remains the configured base/web-vault identity.

Run as the unprivileged operator. No vault session or secret is read.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged operator, not root"

for command in bw curl jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'Checking native Vaultwarden API on %s/api/config...\n' "${LOCAL_BASE}"
local_config="$(
  curl --fail --silent --show-error --max-time 5 "${LOCAL_BASE}/api/config"
)" || fail "native Vaultwarden API is not reachable at ${LOCAL_BASE}/api/config"

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
if [[ "${public_code}" == "200" ]]; then
  printf 'OK: public Vaultwarden client API is reachable: %s/api/config\n' "${PUBLIC_BASE}"
else
  printf 'WARN: public Vaultwarden client API returned HTTP %s; TrueNAS CLI will use loopback endpoints.\n' "${public_code:-000}" >&2
fi

if [[ "${MODE}" == "--check" ]]; then
  printf 'OK: local Vaultwarden client endpoint is ready; run --apply before bw login.\n'
  exit 0
fi

status="$(
  bw status 2>/dev/null | jq -r '.status // "unknown"' 2>/dev/null || printf 'unknown'
)"
if [[ "${status}" != "unauthenticated" ]]; then
  fail "Bitwarden CLI status is ${status}; run 'bw logout' before changing server configuration"
fi

bw config server "${PUBLIC_BASE}" \
  --web-vault "${PUBLIC_BASE}" \
  --api "${LOCAL_BASE}/api" \
  --identity "${LOCAL_BASE}/identity" \
  --icons "${LOCAL_BASE}/icons" \
  --notifications "${LOCAL_BASE}/notifications" \
  --events "${LOCAL_BASE}/events"

configured_base="$(bw config server | tr -d '\r\n')"
[[ "${configured_base%/}" == "${PUBLIC_BASE%/}" ]] ||
  fail "Bitwarden CLI base mismatch after configuration: ${configured_base:-<unset>}"

printf 'OK: Bitwarden CLI base=%s with native API/identity routed through %s\n' \
  "${PUBLIC_BASE}" "${LOCAL_BASE}"
printf 'Next: bw login; export BW_SESSION="$(bw unlock --raw)"; bw sync --session "$BW_SESSION"\n'
