#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="${1:---check}"
FILE="${NABLA_OPTIONAL_APPS_FILE:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/config/truenas/restore-optional-apps.txt}"
case "${MODE}" in
  --check|--stop|--start) ;;
  --help|-h)
    echo "Usage: bash scripts/truenas/restore-optional-apps.sh [--check|--stop|--start]"
    echo "Default --check is read-only. --stop and --start are explicit operator actions."
    exit 0 ;;
  *) echo "ERROR: unknown mode: ${MODE}" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { echo 'ERROR: unexpected arguments' >&2; exit 2; }
[[ -r "${FILE}" ]] || { echo "ERROR: unreadable optional App file: ${FILE}" >&2; exit 2; }
if ! command -v jq >/dev/null 2>&1 || ! command -v midclt >/dev/null 2>&1; then
  echo 'ERROR: jq and midclt are required on TrueNAS' >&2
  exit 2
fi
if [[ "${MODE}" != "--check" && "${EUID}" -ne 0 ]]; then
  echo 'ERROR: --stop/--start require root on TrueNAS' >&2; exit 2
fi

# Never attempt to manipulate core infrastructure even if the optional list
# is misconfigured. Keep the allowlist explicit, not a prefix or regex.
is_protected() {
  case "$1" in
    docker-socket-proxy|pihole|traefik|cloudflared|postgres|redis|kafka|mongo|clickhouse|opensearch|sentry-clickhouse|vaultwarden|garage|crowdsec|adguard-home)
      return 0 ;;
    *) return 1 ;;
  esac
}
mapfile -t apps < <(awk '{sub(/[[:space:]]*#.*/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); if (length($0)) print}' "${FILE}" | LC_ALL=C sort -u)
(( ${#apps[@]} > 0 )) || { echo 'ERROR: empty optional app set' >&2; exit 2; }
for app in "${apps[@]}"; do
  [[ "${app}" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || {
    echo "ERROR: invalid app id: ${app}" >&2; exit 2;
  }
  if is_protected "${app}"; then
    echo "ERROR: protected foundation app cannot be optional: ${app}" >&2; exit 2
  fi
done

state_file="$(mktemp)"
trap 'rm -f "${state_file}"' EXIT
midclt call app.query >"${state_file}"
jq -e 'type == "array"' "${state_file}" >/dev/null || {
  echo 'ERROR: malformed TrueNAS app.query response' >&2; exit 2;
}

failures=0
for app in "${apps[@]}"; do
  state="$(jq -r --arg id "${app}" '[.[] | select(.id == $id) | .state] | if length == 1 then .[0] else "ABSENT" end' "${state_file}")"
  printf '%-24s %-11s' "${app}" "${state}"
  if [[ "${MODE}" == "--check" ]]; then
    printf ' (read-only)\n'
    continue
  fi
  case "${MODE}:${state}" in
    --stop:RUNNING|--stop:DEPLOYING)
      # DEPLOYING may be an in-flight stateful transaction: refuse to interrupt.
      if [[ "${state}" == DEPLOYING ]]; then
        printf ' SKIP in-flight deployment\n'; failures=$((failures+1)); continue
      fi
      printf ' STOP\n'
      if ! midclt call -j app.stop "${app}" >/dev/null; then failures=$((failures+1)); fi ;;
    --start:STOPPED)
      printf ' START\n'
      if ! midclt call -j app.start "${app}" >/dev/null; then failures=$((failures+1)); fi ;;
    --stop:STOPPED|--start:RUNNING)
      printf ' already desired\n' ;;
    --stop:ABSENT|--start:ABSENT)
      printf ' not installed\n' ;;
    *)
      printf ' SKIP unsafe/in-flight state\n'; failures=$((failures+1)) ;;
  esac
done
if ((failures > 0)); then
  echo "ERROR: ${failures} optional App(s) were not changed; inspect TrueNAS lifecycle" >&2
  exit 1
fi
echo "OK: optional app mode=${MODE} completed"
