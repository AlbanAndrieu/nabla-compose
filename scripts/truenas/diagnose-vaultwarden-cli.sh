#!/usr/bin/env bash
# Read-only Vaultwarden/Bitwarden CLI compatibility diagnostics for TrueNAS.
set -euo pipefail

EXPECTED_SERVER="${NABLA_VAULTWARDEN_PUBLIC_BASE:-https://vaultwarden.albandrieu.com}"
CONTAINER="${VAULTWARDEN_CONTAINER:-vaultwarden}"
failures=0
warnings=0

ok() { printf 'OK: %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'ERROR: %s\n' "$*"; failures=$((failures + 1)); }

printf '==> Bitwarden CLI metadata (no session or secrets)\n'
if command -v bw >/dev/null 2>&1; then
  version="$(bw --version 2>/dev/null || true)"
  server="$(bw config server 2>/dev/null || true)"
  status="$(bw status 2>/dev/null | jq -r '.status // "unknown"' 2>/dev/null || true)"
  printf 'cli_version=%s cli_server=%s cli_state=%s\n' "${version:-unknown}" "${server:-unknown}" "${status:-unknown}"
  if [[ "${server%/}" == "${EXPECTED_SERVER%/}" ]]; then
    ok 'Bitwarden CLI canonical base URL'
  else
    fail 'Bitwarden CLI base URL differs from canonical server'
  fi
  [[ "${status}" == unlocked ]] || warn 'CLI is not unlocked; inventory requires an unlocked operator session'
else
  fail 'Bitwarden CLI missing'
fi

printf '\n==> Time synchronization\n'
if command -v timedatectl >/dev/null 2>&1; then
  sync="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
  ntp="$(timedatectl show -p NTP --value 2>/dev/null || true)"
  printf 'ntp_synchronized=%s ntp_service=%s\n' "${sync:-unknown}" "${ntp:-unknown}"
  if [[ "${sync}" == yes ]]; then
    ok 'host clock synchronized'
  else
    warn 'host clock not confirmed synchronized; check TOTP time drift'
  fi
else
  warn 'timedatectl unavailable'
fi

printf '\n==> Vaultwarden container metadata\n'
if command -v docker >/dev/null 2>&1; then
  metadata="$(docker inspect "${CONTAINER}" --format '{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' 2>/dev/null || true)"
  if [[ -n "${metadata}" ]]; then
    IFS='|' read -r image state health <<< "${metadata}"
    printf 'image=%s state=%s health=%s\n' "${image}" "${state}" "${health}"
    if [[ "${state}" == running && "${health}" == healthy ]]; then
      ok 'Vaultwarden runtime healthy'
    else
      warn 'Vaultwarden runtime health not accepted'
    fi
  else
    warn 'Vaultwarden container unavailable to current user; run with Docker-read access, not sudo bw'
  fi
else
  warn 'Docker unavailable'
fi

printf '\n==> Key-ID API compatibility evidence (redacted counts)\n'
if command -v docker >/dev/null 2>&1; then
  logs="$(docker logs --since 2h "${CONTAINER}" 2>/dev/null || true)"
  # Only count specific known-safe endpoint response sequences; never print raw logs.
  requests="$(printf '%s\n' "${logs}" | grep -Fc 'POST /api/accounts/key-management/user-key-id' || true)"
  not_found="$(printf '%s\n' "${logs}" | grep -Fc '404 Not Found' || true)"
  drift="$(printf '%s\n' "${logs}" | grep -Fc 'TOTP Time drift detected' || true)"
  printf 'user_key_id_requests=%s http_404_lines=%s totp_drift_warnings=%s window=2h\n' "${requests}" "${not_found}" "${drift}"
  if ((requests > 0 && not_found > 0)); then
    warn 'Key-ID POST and HTTP 404 observed in same time window; correlate timestamps before attributing the 404'
  fi
fi

printf '\nVaultwarden compatibility summary: failures=%s warnings=%s (read-only; no login, logout, sync, upgrades, or secrets)\n' "${failures}" "${warnings}"
((failures == 0))
