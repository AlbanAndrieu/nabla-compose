#!/usr/bin/env bash
# Read-only Gatus crash triage. Never emit config, environment or raw logs.
set -euo pipefail

for binary in docker stat; do
  command -v "${binary}" >/dev/null 2>&1 || { printf 'ERROR: missing %s\n' "${binary}" >&2; exit 2; }
done

printf '%s\n' '==> Gatus container metadata (no environment)'
if ! docker inspect gatus --format 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} user={{.Config.User}} image={{.Config.Image}}' 2>/dev/null; then
  printf '%s\n' 'ERROR: container gatus not available' >&2
  exit 1
fi
printf '%s\n' '==> Storage and configuration metadata (no file content)'
for path in /mnt/cpool/gatus /mnt/cpool/gatus/gatus.db apps/gatus/config/config.yml; do
  if [[ -e "${path}" ]]; then
    stat -c '%a %u:%g %F %n' -- "${path}"
  else
    printf 'MISSING %s\n' "${path}"
  fi
done
printf '%s\n' '==> Container mount destinations (no source paths)'
docker inspect gatus --format '{{range .Mounts}}{{println .Destination .RW}}{{end}}' 2>/dev/null || exit 1
printf '%s\n' '==> Redacted error-category counts in last 80 log lines'
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
printf '%s\n' 'Diagnostic only; no restart or permission change performed.'
