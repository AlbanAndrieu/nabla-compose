#!/usr/bin/env bash
# Read-only Vaultwarden/Bitwarden CLI compatibility diagnostics for TrueNAS.
set -euo pipefail

EXPECTED_SERVER="${NABLA_VAULTWARDEN_PUBLIC_BASE:-https://vaultwarden.albandrieu.com}"
CONTAINER="${VAULTWARDEN_CONTAINER:-vaultwarden}"
ACCEPTED_CLI="${NABLA_BITWARDEN_CLI_COMPAT_VERSION:-2026.8.0}"
KNOWN_BAD_CLI="${NABLA_BITWARDEN_CLI_KNOWN_BAD_VERSION:-2026.9.0}"
failures=0
warnings=0

ok() { printf 'OK: %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'ERROR: %s\n' "$*"; failures=$((failures + 1)); }

if command -v midclt >/dev/null 2>&1 || [[ -r /etc/version ]]; then
  SCOPE="truenas"
else
  SCOPE="workstation"
fi
printf 'scope=%s\n' "${SCOPE}"

printf '==> Bitwarden CLI metadata (no session or secrets)\n'
if command -v bw >/dev/null 2>&1; then
  cli_path="$(command -v bw)"
  version="$(bw --version 2>/dev/null || true)"
  server="$(bw config server 2>/dev/null || true)"
  status="$(bw status 2>/dev/null | jq -r '.status // "unknown"' 2>/dev/null || true)"
  printf 'cli_path=%s cli_version=%s cli_server=%s cli_state=%s\n' "${cli_path}" "${version:-unknown}" "${server:-unknown}" "${status:-unknown}"
  case "${version}" in
    "${ACCEPTED_CLI}") ok "Bitwarden CLI ${version} runtime-accepted against current Vaultwarden" ;;
    "${KNOWN_BAD_CLI}")
      fail "Bitwarden CLI ${version} is known incompatible here: login triggers KeyIdBackfillError/HTTP 404; use ${ACCEPTED_CLI}"
      ;;
    *) warn "Bitwarden CLI ${version:-unknown} has not been runtime-accepted against current Vaultwarden" ;;
  esac
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
DOCKER_CMD=()
if [[ "${SCOPE}" != "truenas" ]]; then
  printf 'container_scope=skipped-non-truenas\n'
else
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
  fi
fi
fi
if [[ "${SCOPE}" == "truenas" ]] && (( ${#DOCKER_CMD[@]} > 0 )); then
  metadata="$("${DOCKER_CMD[@]}" inspect "${CONTAINER}" --format '{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' 2>/dev/null || true)"
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
elif [[ "${SCOPE}" == "truenas" ]]; then
  warn 'Docker unavailable on TrueNAS'
fi

printf '\n==> Key-ID API compatibility evidence (redacted counts)\n'
if [[ "${SCOPE}" != "truenas" ]]; then
  printf 'logs_scope=skipped-non-truenas\n'
elif (( ${#DOCKER_CMD[@]} == 0 )); then
  warn 'logs_unavailable: Docker access denied; zero errors cannot be inferred'
elif logs="$("${DOCKER_CMD[@]}" logs --since 2h "${CONTAINER}" 2>/dev/null)"; then
  # Never display raw container logs: they can contain authentication data.
  requests="$(printf '%s\n' "${logs}" | grep -Fc 'POST /api/accounts/key-management/user-key-id' || true)"
  not_found="$(printf '%s\n' "${logs}" | grep -Fc '404 Not Found' || true)"
  drift="$(printf '%s\n' "${logs}" | grep -Fc 'TOTP Time drift detected' || true)"
  printf 'logs_available=true user_key_id_requests=%s http_404_lines=%s totp_drift_warnings=%s window=2h\n' "${requests}" "${not_found}" "${drift}"
  if ((requests > 0 && not_found > 0)); then
    if [[ "${version:-}" == "${ACCEPTED_CLI}" ]]; then
      printf 'INFO: historical Key-ID POST/404 evidence matches the already-proven %s incompatibility; current CLI %s is accepted.\n' "${KNOWN_BAD_CLI}" "${ACCEPTED_CLI}"
    else
      warn 'Key-ID POST and HTTP 404 observed while current CLI is not the accepted compatibility pin'
    fi
  fi
else
  warn 'logs_unavailable: cannot read Vaultwarden Docker logs; zero errors cannot be inferred'
fi

printf '\nVaultwarden compatibility summary: failures=%s warnings=%s (read-only; no login, logout, sync, upgrades, or secrets)\n' "${failures}" "${warnings}"
((failures == 0))
