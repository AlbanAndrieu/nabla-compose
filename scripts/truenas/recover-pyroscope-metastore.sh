#!/usr/bin/env bash
# Recover an unhealthy *single-node* Pyroscope 2 metastore without touching other apps.
# --check is read-only. --apply moves historical state into a dated local backup.
set -euo pipefail
umask 077

MODE="${1:---check}"
ACK="${2:-}"
DATA_ROOT=/mnt/cpool/pyroscope/data
CONTAINER=pyroscope
fail() { printf 'BLOCKED Pyroscope recovery: %s\n' "$*" >&2; exit 1; }
usage() {
  printf 'Usage: sudo bash %s --check | --apply RESET_PYROSCOPE_HISTORY\n' "$0" >&2
}
[[ "${MODE}" == --check || "${MODE}" == --apply ]] || { usage; exit 2; }
if [[ "${MODE}" == --apply ]]; then
  [[ "${ACK}" == RESET_PYROSCOPE_HISTORY ]] ||
    fail 'explicit RESET_PYROSCOPE_HISTORY acknowledgement required'
  (( EUID == 0 )) || fail 'sudo required for recovery'
else
  [[ -z "${ACK}" ]] || { usage; exit 2; }
fi
for binary in docker stat mv mkdir date; do
  command -v "${binary}" >/dev/null 2>&1 || fail "missing ${binary}"
done
[[ -d "${DATA_ROOT}" && ! -L "${DATA_ROOT}" ]] || fail 'data root missing or symlink'
user="$(docker inspect "${CONTAINER}" --format '{{.Config.User}}' 2>/dev/null)" ||
  fail 'container cannot be inspected'
mount="$(docker inspect "${CONTAINER}" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/pyroscope"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null)" ||
  fail 'container data bind cannot be inspected'
[[ "${user}" == '568:568' ]] || fail 'unexpected container identity'
[[ "${mount}" == "${DATA_ROOT}" ]] || fail 'unexpected data mount; refusing recovery'
[[ "$(stat -c '%u:%g' -- "${DATA_ROOT}")" == '568:568' ]] ||
  fail 'data root not owned by expected UID/GID 568:568'
declare -a state_paths=()
for relative in v1 v2 data; do
  path="${DATA_ROOT}/${relative}"
  if [[ -e "${path}" || -L "${path}" ]]; then
    [[ -d "${path}" && ! -L "${path}" ]] || fail 'unexpected state path type'
    state_paths+=("${path}")
  fi
done
printf 'container=%s identity=%s mount=verified directories=%s mode=%s\n' \
  "${CONTAINER}" "${user}" "${#state_paths[@]}" "${MODE}"
if [[ "${MODE}" == --check ]]; then
  printf 'READ_ONLY: no stop, reset, cleanup or state mutation performed\n'
  exit 0
fi
(( "${#state_paths[@]}" > 0 )) || fail 'no known historical state to reset'
backup="${DATA_ROOT}/.metastore-backup-$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "${backup}" ]] || fail 'backup path already exists'
# Do not touch storage if Docker cannot stop the exact container.
docker stop --time 20 "${CONTAINER}" >/dev/null || fail 'stop failed'
running="$(docker inspect "${CONTAINER}" --format '{{.State.Running}}')" ||
  fail 'cannot prove stop'
[[ "${running}" == false ]] || fail 'container still running; no state moved'
mkdir -m 0700 -- "${backup}"
for path in "${state_paths[@]}"; do
  relative="${path##*/}"
  [[ -d "${path}" && ! -L "${path}" ]] || fail 'state changed after stop'
  mv -- "${path}" "${backup}/${relative}"
done
printf 'BACKUP_CREATED: %s (history retained for explicit later disposal)\n' "${backup}"
docker start "${CONTAINER}" >/dev/null || fail 'start failed; backup preserved'
printf 'RESTART_REQUESTED: verify HTTP :4040/ and /metrics; no readiness assumed\n'
