#!/usr/bin/env bash
set -euo pipefail

# Shared compact/full diagnostic bootstrap.
NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/diagnostic.sh
source "$(dirname -- "${NABLA_SCRIPT_DIR}")/lib/diagnostic.sh"
nabla_diagnostic_maybe_wrap "${BASH_SOURCE[0]}" "$@"

CONTAINER="${PYROSCOPE_CONTAINER:-pyroscope}"
READY_URL="${PYROSCOPE_READY_URL:-http://172.17.0.24:4040/}"
METRICS_URL="${PYROSCOPE_METRICS_URL:-http://172.17.0.24:4040/metrics}"
DATA_ROOT="${PYROSCOPE_DATA_ROOT:-/mnt/cpool/pyroscope/data}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in curl docker du df find stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'Pyroscope diagnostic container=%s ready=%s data=%s\n' \
  "${CONTAINER}" "${READY_URL}" "${DATA_ROOT}"

contract_failed=0
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

printf '\n=== Effective working directory and storage contract ===\n'
actual_workdir="$(docker inspect "${CONTAINER}" --format '{{.Config.WorkingDir}}')"
actual_user="$(docker inspect "${CONTAINER}" --format '{{.Config.User}}')"
actual_state="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}')"
mount_root="$(docker inspect "${CONTAINER}" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/pyroscope"}}{{.Source}}{{end}}{{end}}')"
printf 'workdir=%s user=%s state=%s storage_mount=%s\n' "${actual_workdir}" "${actual_user}" "${actual_state}" "${mount_root:-absent}"
if [[ "${actual_workdir}" != /var/lib/pyroscope ]]; then
  printf 'FAIL: relative metastore path ./data/v2 resolves outside the expected persistent directory\n' >&2
  contract_failed=1
fi
if [[ "${mount_root}" != "${DATA_ROOT}" ]]; then
  printf 'FAIL: expected persistent metastore mount is not active\n' >&2
  contract_failed=1
fi
if [[ "${actual_state}" != running ]]; then
  printf 'FAIL: Pyroscope runtime is not running\n' >&2
  contract_failed=1
fi

printf '\n=== Mounts ===\n'
docker inspect "${CONTAINER}" \
  --format '{{range .Mounts}}{{println .Source "->" .Destination "rw=" .RW}}{{end}}'

printf '\n=== Persistent storage ownership ===\n'
if [[ -d "${DATA_ROOT}" ]]; then
  stat -c 'owner=%u:%g mode=%a path=%n' "${DATA_ROOT}"
  owner_uid="$(stat -c '%u' "${DATA_ROOT}")"
  owner_gid="$(stat -c '%g' "${DATA_ROOT}")"
  mode="$(stat -c '%a' "${DATA_ROOT}")"
  container_uid="${actual_user%%:*}"
  # .Config.User may be a name (pyroscope), while docker top reports UID 10001."
  printf 'container_user=%s\n' "${container_uid}"
  if [[ "${container_uid}" =~ ^[0-9]+$ ]] && [[ "${owner_uid}" != "${container_uid}" ]]; then
    # Do not infer supplementary groups from a numeric UID. Report a potential
    # mismatch for the operator to validate rather than mutate permissions.
    printf 'WARNING: data owner UID differs from container UID; verify effective write permission\n'
  fi
  if [[ "${container_uid}" =~ ^[0-9]+$ && "${owner_uid}" != "${container_uid}" && "${owner_gid}" == 0 && "${mode}" == 770 ]]; then
    printf 'ERROR: root:root 770 bind mount is not writable by an unprivileged UID without supplementary root group\n' >&2
  fi
fi

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
if [[ "${http_status}" != 200 ]]; then contract_failed=1; fi
metrics_status="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "${METRICS_URL}" || true)"
printf 'METRICS HTTP %s %s\n' "${metrics_status:-000}" "${METRICS_URL}"
if [[ "${metrics_status}" != 200 ]]; then contract_failed=1; fi
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
if ((contract_failed > 0)); then fail "Pyroscope runtime/storage/readiness contract incomplete"; fi
printf 'PASS: Pyroscope runtime/storage/readiness contract\n'
