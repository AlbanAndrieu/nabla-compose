#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${SURICATA_CONTAINER:-suricata}"
INTERFACE="${SURICATA_INTERFACE:-br0}"
LOG_TAIL="${SURICATA_LOG_TAIL:-120}"

printf 'Suricata diagnostic container=%s interface=%s\n' "${CONTAINER}" "${INTERFACE}"

if ip link show "${INTERFACE}" >/dev/null 2>&1; then
  printf 'OK: host interface %s exists\n' "${INTERFACE}"
else
  printf 'ERROR: host interface %s does not exist\n' "${INTERFACE}" >&2
  printf 'Available host interfaces:\n' >&2
  ip -o link show | awk -F': ' '{print "  " $2}' >&2
  exit 1
fi

if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  printf 'ERROR: Docker container %s does not exist\n' "${CONTAINER}" >&2
  exit 1
fi

printf '\n=== Docker state ===\n'
docker inspect "${CONTAINER}" --format \
  'status={{.State.Status}} running={{.State.Running}} restarting={{.State.Restarting}} pid={{.State.Pid}} exit={{.State.ExitCode}} restarts={{.RestartCount}} error={{.State.Error}}'

printf '\n=== Effective command/environment ===\n'
docker inspect "${CONTAINER}" --format 'path={{.Path}} args={{json .Args}}'
docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' |
  grep -E '^(SURICATA_OPTIONS|PUID|PGID|ENABLE_CRON|TZ)=' || true

printf '\n=== Mounts ===\n'
docker inspect "${CONTAINER}" --format \
  '{{range .Mounts}}{{println .Source "->" .Destination "rw=" .RW}}{{end}}'

printf '\n=== Recent logs ===\n'
docker logs --tail "${LOG_TAIL}" "${CONTAINER}" 2>&1 || true

printf '\n=== Persistent paths ===\n'
for path in /mnt/cpool/suricata/etc /mnt/cpool/suricata/lib /mnt/cpool/suricata/log; do
  if [[ -e "${path}" ]]; then
    stat -c '%A %U:%G %n' "${path}"
  else
    printf 'MISSING %s\n' "${path}"
  fi
done

printf '\nREAD-ONLY: no container or TrueNAS App state changed.\n'
