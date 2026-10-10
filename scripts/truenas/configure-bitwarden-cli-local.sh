#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
PUBLIC_BASE="${NABLA_VAULTWARDEN_PUBLIC_BASE:-https://vaultwarden.albandrieu.com}"
LOCAL_ORIGIN="${NABLA_VAULTWARDEN_LOCAL_ORIGIN:-http://127.0.0.1:30032}"
LOCAL_LAN_IP="${NABLA_VAULTWARDEN_LOCAL_LAN_IP:-172.17.0.24}"
LAN_RESOLVER="${NABLA_LAN_RESOLVER:-172.17.0.1}"
PUBLIC_RESOLVER="${NABLA_PUBLIC_RESOLVER:-1.1.1}"
PUBLIC_RESOLVER_SOURCE="${NABLA_PUBLIC_RESOLVER:+environment}"
PUBLIC_RESOLVER_SOURCE="${PUBLIC_RESOLVER_SOURCE:-default}"
PUBLIC_HOST="${PUBLIC_BASE#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply | --flush-host-cache) ;;
  -h | --help)
    cat <<'EOF'
usage: bash scripts/truenas/configure-bitwarden-cli-local.sh [--check|--apply|--flush-host-cache]

Validate the local Vaultwarden origin, then configure the official Bitwarden
CLI with the canonical HTTPS Vaultwarden server.

The local HTTP origin is a health probe only. Bitwarden CLI 2026.x intentionally
rejects insecure API and identity URLs, including loopback URLs. Operational use
requires a working HTTPS client endpoint before login or secret materialization.

--flush-host-cache invalidates only the nscd hosts cache, then reruns the
Vaultwarden HTTPS check. It does not restart networking, DNS, pfSense or Vaultwarden.
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

if [[ "${MODE}" == "--flush-host-cache" ]]; then
  command -v nscd >/dev/null 2>&1 ||
    fail "nscd is not installed; no nscd hosts cache can be invalidated"
  pgrep -x nscd >/dev/null 2>&1 ||
    fail "nscd is installed but not running; investigate another resolver/cache layer"
  printf 'Invalidating only the nscd hosts cache...\n'
  sudo nscd -i hosts
  printf 'OK: nscd hosts cache invalidated\n'
  MODE="--check"
fi

diagnose_public_dns() {
  local system_ips=""
  local lan_ips=""
  local public_ips=""

  if command -v getent >/dev/null 2>&1; then
    system_ips="$(getent ahostsv4 "${PUBLIC_HOST}" 2>/dev/null | awk '{print $1}' | sort -u | paste -sd, - || true)"
  fi
  if command -v dig >/dev/null 2>&1; then
    lan_ips="$(dig +short A "${PUBLIC_HOST}" @"${LAN_RESOLVER}" 2>/dev/null | sort -u | paste -sd, - || true)"
    public_ips="$(dig +short A "${PUBLIC_HOST}" @"${PUBLIC_RESOLVER}" 2>/dev/null | sort -u | paste -sd, - || true)"
  fi

  printf 'vaultwarden_public_host=%s system_ips=%s lan_resolver_ips=%s public_resolver=%s public_resolver_source=%s public_resolver_ips=%s\n' \
    "${PUBLIC_HOST}" "${system_ips:-<unknown>}" "${lan_ips:-<unknown>}" "${PUBLIC_RESOLVER}" "${PUBLIC_RESOLVER_SOURCE}" "${public_ips:-<unknown>}"

  if [[ ",${system_ips}," == *",${LOCAL_LAN_IP},"* ]]; then
    if [[ ",${lan_ips}," == *",${LOCAL_LAN_IP},"* ]]; then
      printf 'ERROR: split-DNS detected: %s resolves to local TrueNAS IP %s from pfSense/Unbound and the system resolver.\n' \
        "${PUBLIC_HOST}" "${LOCAL_LAN_IP}" >&2
      printf 'ERROR: remove the public pfSense/Unbound Host Override; keep vaultwarden.int.albandrieu.com for direct LAN access if needed.\n' >&2
      printf 'ERROR: do not edit /var/unbound/host_entries.conf directly; it is generated from pfSense configuration.\n' >&2
    else
      printf 'ERROR: TrueNAS system resolver still maps %s to %s while pfSense/Unbound no longer does.\n' \
        "${PUBLIC_HOST}" "${LOCAL_LAN_IP}" >&2
      if grep -Eq "(^|[[:space:]])${LOCAL_LAN_IP}([[:space:]]+.*[[:space:]])?${PUBLIC_HOST}([[:space:]]|$)" /etc/hosts 2>/dev/null; then
        printf 'ERROR: /etc/hosts contains a local override for %s. Remove it through the TrueNAS-supported configuration path rather than editing generated state blindly.\n' \
          "${PUBLIC_HOST}" >&2
      else
        if pgrep -x nscd >/dev/null 2>&1; then
          printf 'INFO: nscd is running; a stale hosts cache can explain this mismatch. Run this helper with --flush-host-cache.\n' >&2
        else
          printf 'INFO: no matching /etc/hosts entry detected; inspect hosts: ordering in /etc/nsswitch.conf and any local resolver/cache before changing pfSense again.\n' >&2
        fi
        grep -E '^[[:space:]]*hosts:' /etc/nsswitch.conf 2>/dev/null || true
        grep -E '^[[:space:]]*nameserver[[:space:]]+' /etc/resolv.conf 2>/dev/null || true
        if command -v resolvectl >/dev/null 2>&1; then
          resolvectl query "${PUBLIC_HOST}" 2>/dev/null || true
        fi
      fi
    fi
    return 1
  fi

  if [[ ",${lan_ips}," == *",${LOCAL_LAN_IP},"* ]]; then
    printf 'ERROR: pfSense/Unbound still maps %s to local TrueNAS IP %s although the system resolver currently does not.\n' \
      "${PUBLIC_HOST}" "${LOCAL_LAN_IP}" >&2
    return 1
  fi
}

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
    diagnose_public_dns || true
    return 1
  fi
  diagnose_public_dns || return 1
  printf 'OK: canonical HTTPS Vaultwarden client API is reachable through the public hostname: %s/api/config\n' "${PUBLIC_BASE}"
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
bw config server "${PUBLIC_BASE}" \
  --web-vault "${PUBLIC_BASE}" \
  --api "${PUBLIC_BASE}/api" \
  --identity "${PUBLIC_BASE}/identity" \
  --icons "${PUBLIC_BASE}/icons" \
  --notifications "${PUBLIC_BASE}/notifications" \
  --events "${PUBLIC_BASE}/events"

configured_after="$(bw config server 2>/dev/null | tr -d '\r\n' || true)"
[[ "${configured_after}" == "${PUBLIC_BASE}" ]] ||
  fail "Bitwarden CLI base URL did not persist canonical HTTPS origin"
printf 'OK: Bitwarden CLI base and per-service endpoints set to canonical HTTPS origin %s\n' "${PUBLIC_BASE}"

check_public_api ||
  fail "CLI overrides are now HTTPS-only, but canonical Vaultwarden ingress still returns a non-200 /api/config; fix the tunnel/origin route before login"
