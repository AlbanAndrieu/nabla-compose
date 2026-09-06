#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in docker git jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"

declare -A states=()
while IFS=$'\t' read -r app_id state; do
  [[ -n "${app_id}" ]] || continue
  states["${app_id}"]="${state}"
done < <(jq -r '.[] | [(.id // .name), (.state // "UNKNOWN")] | @tsv' "${tmp}")

declare -A app_alias=(
  [2fauth]="twofactor-auth"
  [elasticsearch]="elastic-search"
  [homeassistant]="home-assistant"
  [reactive]="reactive-resume"
)

running=0
stopped=0
crashed=0
deploying=0
missing=0
other=0

printf '🔎 repository-backed TrueNAS application inventory\n'
printf '%-26s %-26s %-12s\n' "REPOSITORY APP" "TRUENAS APP" "STATE"
printf '%-26s %-26s %-12s\n' "--------------------------" "--------------------------" "------------"

while IFS= read -r compose_path; do
  app="$(basename "$(dirname "${compose_path}")")"
  runtime_id="${app_alias[${app}]-${app}}"
  state="${states[${runtime_id}]-MISSING}"

  printf '%-26s %-26s %-12s\n' "${app}" "${runtime_id}" "${state}"

  case "${state}" in
    RUNNING)
      ((running += 1))
      ;;
    STOPPED)
      ((stopped += 1))
      ;;
    CRASHED)
      ((crashed += 1))
      ;;
    DEPLOYING)
      ((deploying += 1))
      ;;
    MISSING)
      ((missing += 1))
      ;;
    *)
      ((other += 1))
      ;;
  esac
done < <(git -C "${ROOT}" ls-files 'apps/*/compose.yml' | sort)

printf '\nSummary: RUNNING=%d STOPPED=%d CRASHED=%d DEPLOYING=%d MISSING=%d OTHER=%d\n' \
  "${running}" "${stopped}" "${crashed}" "${deploying}" "${missing}" "${other}"

printf '\n🔎 problematic Docker container states\n'
problematic="$(
  docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' |
    awk 'BEGIN { IGNORECASE=1 } /Restarting|unhealthy|Dead|Created/ || (/Exited \(/ && $0 !~ /Exited \(0\)/)'
)"

if [[ -n "${problematic}" ]]; then
  printf '%s\n' "${problematic}"
else
  printf '✅ no restarting, unhealthy, non-zero exited, dead or created containers detected\n'
fi
