#!/usr/bin/env bash
set -euo pipefail

if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  WRAPPER="$(dirname -- "${SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${WRAPPER}" "${SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

CONTAINER="${PYROSCOPE_CONTAINER:-pyroscope}"
READY_URL="${PYROSCOPE_READY_URL:-http://127.0.0.1:4040/ready}"
DATA_ROOT="${PYROSCOPE_DATA_ROOT:-/mnt/cpool/pyroscope/data}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in curl docker du df find; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'Pyroscope diagnostic container=%s ready=%s data=%s\n' \
  "${CONTAINER}" "${READY_URL}" "${DATA_ROOT}"

printf '\n=== Docker state ===\n'
if docker inspect "${CONTAINER}" \
  --format 'status={{.State.Status}} running={{.State.Running}} restarting={{.State.Restarting}} pid={{.State.Pid}} exit={{.State.ExitCode}} restarts={{.RestartCount}} error={{.State.Error}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'; then
  :
else
  fail "container ${CONTAINER} is not inspectable"
fi

printf '\n=== Effective image/command ===\n'
docker inspect "${CONTAINER}" \
  --format 'image={{.Config.Image}} path={{.Path}} args={{json .Args}}'

printf '\n=== Mounts ===\n'
docker inspect "${CONTAINER}" \
  --format '{{range .Mounts}}{{println .Source "->" .Destination "rw=" .RW}}{{end}}'

printf '\n=== Readiness ===\n'
ready_tmp="$(mktemp)"
trap 'rm -f "${ready_tmp}"' EXIT
http_status="$(
  curl --silent --show-error --max-time 5 \
    --output "${ready_tmp}" \
    --write-out '%{http_code}' \
    "${READY_URL}" || true
)"
printf 'HTTP %s %s\n' "${http_status:-000}" "${READY_URL}"
if [[ -s "${ready_tmp}" ]]; then
  head -c 2048 "${ready_tmp}"
  printf '\n'
fi

printf '\n=== Persistent data ===\n'
if [[ -d "${DATA_ROOT}" ]]; then
  du -sh "${DATA_ROOT}" 2>/dev/null || true
  df -h "${DATA_ROOT}" 2>/dev/null || true
  for relative in v1 v2 v2/metastore/raft v2/metastore/data v2/shared; do
    path="${DATA_ROOT}/${relative}"
    if [[ -e "${path}" ]]; then
      printf '%s: ' "${path}"
      du -sh "${path}" 2>/dev/null || true
    else
      printf 'MISSING: %s\n' "${path}"
    fi
  done
  printf 'Recent metastore files:\n'
  find "${DATA_ROOT}/v2" -maxdepth 4 -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' 2>/dev/null |
    sort -r |
    head -n 20 || true
else
  printf 'MISSING: %s\n' "${DATA_ROOT}"
fi

printf '\n=== Recent logs ===\n'
docker logs --tail 200 "${CONTAINER}" 2>&1 || true

printf '\nREAD-ONLY: no container, dataset, Raft or TrueNAS App state changed.\n'
