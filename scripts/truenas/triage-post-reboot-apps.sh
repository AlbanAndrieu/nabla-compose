#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

# Read-only, bounded post-reboot triage. No restart, upgrade or secret values.
for command in midclt jq docker; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "ERROR: missing $command" >&2; exit 2;
  }
done
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
midclt call app.query >"$tmp"
jq -e 'type=="array"' "$tmp" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "$tmp" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro mcp-cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "$app" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "$tmp"
done
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
