#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${FASTAPI_SAMPLE_URL:-http://127.0.0.1:8091}"
ATTEMPTS="${FASTAPI_HEALTH_BOARD_ATTEMPTS:-12}"
INTERVAL="${FASTAPI_HEALTH_BOARD_INTERVAL_SECONDS:-2}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/truenas/check-fastapi-health-board.sh [options]

HTTP-only FastAPI Sample health-board check. No SSH or diagnostics secret is
required.

Options:
  --url URL       FastAPI Sample base URL.
                  Default: http://127.0.0.1:8091
  --attempts N    Maximum health-board polls after refresh. Default: 12
  --interval SEC  Seconds between polls. Default: 2
  -h, --help      Show this help.

Examples:
  scripts/truenas/check-fastapi-health-board.sh
  scripts/truenas/check-fastapi-health-board.sh \
    --url https://fastapi-sample.fastapicloud.dev
EOF
}

while (($#)); do
  case "$1" in
    --url)
      shift
      (($# > 0)) || fail "--url requires a value"
      BASE_URL="${1%/}"
      ;;
    --attempts)
      shift
      (($# > 0)) || fail "--attempts requires a value"
      ATTEMPTS="$1"
      ;;
    --interval)
      shift
      (($# > 0)) || fail "--interval requires a value"
      INTERVAL="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

[[ "${ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] || fail "--attempts must be a positive integer"
[[ "${INTERVAL}" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "--interval must be numeric"

for command in curl jq sleep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

endpoint="${BASE_URL}/api/health-board"
printf 'FastAPI health-board target: %s\n' "${endpoint}"
printf 'Transport: HTTP(S) only; SSH and DIAGNOSTICS_ACCESS_KEY are not used.\n'

# Trigger a refresh but do not treat the immediate response as authoritative:
# health-board refresh is intentionally backgrounded and may return state=pending.
curl -fsS --connect-timeout 4 --max-time 12 \
  -H 'Accept: application/json' \
  "${endpoint}?refresh=true" >/dev/null ||
  fail "unable to request health-board refresh from ${endpoint}"

payload=""
for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  payload="$(
    curl -fsS --connect-timeout 4 --max-time 12 \
      -H 'Accept: application/json' \
      "${endpoint}"
  )" || fail "health-board fetch failed on attempt ${attempt}"

  state="$(jq -r '.state // "unknown"' <<<"${payload}")"
  refreshing="$(jq -r '.refreshing // false' <<<"${payload}")"
  if jq -e '.homelab != null' >/dev/null 2>&1 <<<"${payload}"; then
    printf 'Health-board converged: attempt=%d state=%s refreshing=%s\n' \
      "${attempt}" "${state}" "${refreshing}"
    break
  fi

  printf 'Health-board pending: attempt=%d/%d state=%s refreshing=%s\n' \
    "${attempt}" "${ATTEMPTS}" "${state}" "${refreshing}" >&2

  if ((attempt == ATTEMPTS)); then
    jq '{
      state,
      refreshing,
      age_seconds,
      generated_at,
      error,
      retry_after_seconds,
      homelab_present: (.homelab != null)
    }' <<<"${payload}"
    fail "health-board did not produce homelab evidence within the polling window"
  fi
  sleep "${INTERVAL}"
done

jq '{
  health_board: {
    state,
    refreshing,
    age_seconds,
    generated_at,
    error
  },
  truenas: (.homelab.truenas // {}) | {
    state,
    appliance_state,
    public_ingress_state,
    public: (.public // {}),
    api: (.api // {}) | {
      reachable,
      phase,
      stage,
      authenticated,
      authentication_succeeded,
      version,
      method,
      error,
      stale,
      cached
    },
    diagnostics: (.diagnostics // {}) | {
      path_mode,
      target,
      connect_target,
      error_kind,
      timed_out,
      stages
    }
  },
  pfsense: (.homelab.pfsense.dns // {}) | {
    configured,
    reachable,
    transport_reachable,
    api_authenticated,
    api_evidence_state,
    policy_state,
    reason,
    error_stage,
    error,
    endpoint_status,
    security_filters,
    ingress_block
  }
}' <<<"${payload}"
