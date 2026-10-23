#!/usr/bin/env bash
# Read-only Gatus crash triage. Never emit config, environment or raw logs.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

for binary in docker stat curl jq; do
  command -v "${binary}" >/dev/null 2>&1 || { printf 'ERROR: missing %s\n' "${binary}" >&2; exit 2; }
done

diag_section '' 'Gatus container metadata (no environment)'
if ! docker inspect gatus --format 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} user={{.Config.User}} image={{.Config.Image}}' 2>/dev/null; then
  printf '%s\n' 'ERROR: container gatus not available' >&2
  exit 1
fi
diag_section '' 'Storage and configuration metadata (no file content)'
for path in /mnt/cpool/gatus /mnt/cpool/gatus/gatus.db apps/gatus/config/config.yml; do
  if [[ -e "${path}" ]]; then
    stat -c '%a %u:%g %F %n' -- "${path}"
  else
    printf 'MISSING %s\n' "${path}"
  fi
done
diag_section '' 'Container mount destinations (no source paths)'
docker inspect gatus --format '{{range .Mounts}}{{println .Destination .RW}}{{end}}' 2>/dev/null || exit 1
diag_section '' 'Redacted error-category counts in last 80 log lines'
# Categories are counted only. Never echo raw logs: endpoints and headers may contain secrets.
if ! docker logs --tail 80 gatus 2>&1 | awk '
  BEGIN { IGNORECASE=1 }
  { l=tolower($0); if(l ~ /permission denied|operation not permitted/) p++;
    if(l ~ /sqlite|database|disk i\/o/) d++;
    if(l ~ /yaml|parse|configuration|config/) c++;
    if(l ~ /panic|fatal/) f++;
    n++ }
  END {printf "sample_lines=%d permission=%d database=%d config=%d fatal=%d\n", n,p,d,c,f}
'; then
  printf '%s\n' 'ERROR: cannot read Gatus log categories' >&2
  exit 1
fi
diag_info 'Diagnostic only; no restart or permission change performed.'

diag_section '' 'Gatus HTTP functional evidence (no response bodies)'
GATUS_URL="${GATUS_URL:-http://172.17.0.24:8085}"
for endpoint in / /api/v1/endpoints/statuses; do
  status="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "${GATUS_URL}${endpoint}" || true)"
  printf 'endpoint=%s http=%s\n' "${endpoint}" "${status:-000}"
  if [[ "${status}" == 000 ]]; then
    printf 'WARN Gatus HTTP unreachable on %s\n' "${endpoint}"
  fi
done
printf '%s\n' 'HTTP 200 is transport evidence only; API contract and monitored endpoint status require separate acceptance.'

diag_section '' 'Gatus API monitor evidence (aggregate counts, no URLs or identities)'
# The API reports each monitor with a result history; only the LAST result
# establishes its current state. A populated list alone does not prove health.
# Do not expose names, endpoint URLs, probe response bodies or credentials.
api_counts="$(curl --silent --show-error --fail --max-time 8 \
  "${GATUS_URL}/api/v1/endpoints/statuses" |
  jq -er '
    if type != "array" then error("unexpected API payload") else
      [ .[] |
        if type != "object" then "unknown"
        elif (.results | type) != "array" then "unknown"
        elif (.results | length) == 0 then "pending"
        elif (.results[-1] | type) != "object" then "unknown"
        elif (.results[-1].success | type) != "boolean" then "unknown"
        elif .results[-1].success then "up"
        else "down" end
      ] as $states
      | [($states | length),
         ($states | map(select(. == "up")) | length),
         ($states | map(select(. == "down")) | length),
         ($states | map(select(. == "pending")) | length),
         ($states | map(select(. == "unknown")) | length)]
      | map(tostring) | join(" ")
    end
  ' 2>/dev/null)" || {
  echo 'WARN Gatus API monitor status unavailable or structurally invalid'
  exit 2
}
read -r monitors up down pending unknown <<< "${api_counts}"
printf 'monitors=%s up=%s down=%s pending=%s unknown=%s\n' \
  "${monitors}" "${up}" "${down}" "${pending}" "${unknown}"
if ((monitors == 0)); then
  echo 'WARN Gatus API contains no monitors; cannot confirm monitoring coverage'
  exit 2
fi
if ((down > 0 || pending > 0 || unknown > 0)); then
  echo 'WARN Some configured targets are DOWN, have no samples or have unrecognized results'
  echo 'INFO Target health does not imply Gatus itself is unavailable'
else
  echo 'OK Gatus monitor results are present and currently UP'
fi
diag_info 'Monitor identity parity with the generated catalog requires a separate inventory comparison.'
