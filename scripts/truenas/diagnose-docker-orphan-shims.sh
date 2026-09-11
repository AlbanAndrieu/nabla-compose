#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TARGET="${2:-}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
  sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --recover <container>
EOF
}

case "${MODE}" in
  --check)
    [[ -z "${TARGET}" ]] || fail "--check does not accept a container"
    ;;
  --recover)
    [[ -n "${TARGET}" ]] || { usage; fail "--recover requires an exact container name or id"; }
    ;;
  *)
    usage
    exit 2
    ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in docker jq pgrep awk kill ps; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

find_shim_pids() {
  local cid="$1"
  pgrep -af containerd-shim-runc-v2 |
    awk -v cid="${cid}" 'index($0, "-id " cid) {print $1}'
}

container_snapshot() {
  local target="$1"
  docker inspect "${target}" |
    jq -r '.[0] |
      [
        .Id,
        (.Name | ltrimstr("/")),
        (.State.Status // "unknown"),
        ((.State.Running // false) | tostring),
        ((.State.Restarting // false) | tostring),
        ((.State.Pid // 0) | tostring),
        ((.RestartCount // 0) | tostring)
      ] | @tsv'
}

if [[ "${MODE}" == "--check" ]]; then
  candidates=0

  printf 'Docker/containerd orphan-shim diagnostic (read-only)\n'
  printf 'CONTAINER\tSTATUS\tRUNNING\tRESTARTING\tPID\tRESTARTS\tSHIM_PIDS\n'

  while IFS= read -r cid; do
    [[ -n "${cid}" ]] || continue

    row="$(container_snapshot "${cid}")"
    IFS=$'\t' read -r full_id name status running restarting pid restarts <<<"${row}"

    if [[ "${pid}" == "0" && ( "${running}" == "true" || "${restarting}" == "true" ) ]]; then
      mapfile -t shim_pids < <(find_shim_pids "${full_id}")
      shim_text="${shim_pids[*]:-none}"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "${name}" "${status}" "${running}" "${restarting}" "${pid}" "${restarts}" "${shim_text}"
      candidates=$((candidates + 1))
    fi
  done < <(docker ps -aq)

  if ((candidates == 0)); then
    printf 'OK: no Docker container reports Running/Restarting with pid=0\n'
  else
    warn "${candidates} Docker container(s) have runtime state without a live init PID"
    warn "verify the exact container id and shim before any recovery; never kill shims in bulk"
  fi

  exit 0
fi

# --recover is intentionally narrow. It is valid only when Docker says the
# workload is running/restarting but there is no container init PID. This
# avoids signaling a live workload and never restarts Docker/containerd.
row="$(container_snapshot "${TARGET}")" || fail "unable to inspect ${TARGET}"
IFS=$'\t' read -r cid name status running restarting pid restarts <<<"${row}"

printf 'Recovery target:\n'
printf '  container=%s\n' "${name}"
printf '  id=%s\n' "${cid}"
printf '  status=%s running=%s restarting=%s pid=%s restart_count=%s\n' \
  "${status}" "${running}" "${restarting}" "${pid}" "${restarts}"

[[ "${pid}" == "0" ]] ||
  fail "${name}: live init PID ${pid} exists; refusing orphan-shim recovery"
[[ "${running}" == "true" || "${restarting}" == "true" ]] ||
  fail "${name}: container is not in a running/restarting ghost state"

mapfile -t shim_pids < <(find_shim_pids "${cid}")
((${#shim_pids[@]} == 1)) ||
  fail "${name}: expected exactly one containerd shim for ${cid}, found ${#shim_pids[@]}"

shim_pid="${shim_pids[0]}"
shim_cmd="$(ps -o args= -p "${shim_pid}" 2>/dev/null || true)"
[[ "${shim_cmd}" == *"containerd-shim-runc-v2"* && "${shim_cmd}" == *"-id ${cid}"* ]] ||
  fail "${name}: shim PID ${shim_pid} no longer matches the exact container id"

printf '  shim_pid=%s\n' "${shim_pid}"
printf '  shim=%s\n' "${shim_cmd}"

printf 'Disabling restart policy before shim recovery...\n'
docker update --restart=no "${cid}" >/dev/null

printf 'Sending SIGTERM to orphan shim PID %s...\n' "${shim_pid}"
kill -TERM "${shim_pid}"

deadline=$((SECONDS + 5))
while ((SECONDS < deadline)); do
  kill -0 "${shim_pid}" 2>/dev/null || break
  sleep 1
done

if kill -0 "${shim_pid}" 2>/dev/null; then
  warn "shim ${shim_pid} ignored SIGTERM; sending SIGKILL to that exact shim only"
  kill -KILL "${shim_pid}"
fi

deadline=$((SECONDS + 10))
while ((SECONDS < deadline)); do
  kill -0 "${shim_pid}" 2>/dev/null || break
  sleep 1
done

kill -0 "${shim_pid}" 2>/dev/null &&
  fail "${name}: orphan shim ${shim_pid} is still alive"

deadline=$((SECONDS + 15))
while ((SECONDS < deadline)); do
  row="$(container_snapshot "${cid}" 2>/dev/null || true)"
  [[ -n "${row}" ]] || break
  IFS=$'\t' read -r _ _ status running restarting pid _ <<<"${row}"
  if [[ "${running}" == "false" && "${restarting}" == "false" && "${pid}" == "0" ]]; then
    break
  fi
  sleep 1
done

printf 'Post-recovery Docker state:\n'
docker inspect "${cid}" 2>/dev/null |
  jq '.[0].State' || true

row="$(container_snapshot "${cid}" 2>/dev/null || true)"
if [[ -n "${row}" ]]; then
  IFS=$'\t' read -r _ _ status running restarting pid _ <<<"${row}"
  [[ "${running}" == "false" && "${restarting}" == "false" && "${pid}" == "0" ]] ||
    fail "${name}: Docker state did not converge after orphan-shim recovery"
fi

printf 'OK: orphan shim recovery completed for %s; retry the supported TrueNAS app.stop operation\n' "${name}"
