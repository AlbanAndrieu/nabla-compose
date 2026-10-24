#!/usr/bin/env bash
# Read-only, bounded post-repair diagnosis for the two observability containers.
# Do not print raw logs, Docker environment, credentials, or full mount paths.
set -euo pipefail

if [[ "${#}" -ne 1 || "${1}" != --check ]]; then
  printf 'Usage: sudo bash %s --check\n' "${0}" >&2
  exit 2
fi
for binary in docker curl timeout; do
  command -v "${binary}" >/dev/null 2>&1 || {
    printf 'MISSING_TOOL: %s\n' "${binary}" >&2
    exit 2
  }
done
failures=0

check_container() {
  local name="${1}" url="${2}" meta logs status exit_code oom restarts
  local http_code curl_exit category
  if ! meta="$(timeout 8 docker inspect --format \
    '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.RestartCount}}' \
    "${name}" 2>/dev/null)"; then
    printf '%s: docker_state=unavailable\n' "${name}"
    failures=$((failures + 1))
    return
  fi
  if [[ ! "${meta}" =~ ^(running|restarting|exited|created|dead|paused)\|[0-9]+\|(true|false)\|[0-9]+$ ]]; then
    printf '%s: docker_state=invalid_metadata\n' "${name}"
    failures=$((failures + 1))
    return
  fi
  IFS='|' read -r status exit_code oom restarts <<< "${meta}"
  printf '%s: state=%s exit=%s oom=%s restarts=%s\n' \
    "${name}" "${status}" "${exit_code}" "${oom}" "${restarts}"

  # Logs are classified in memory. Never emit raw Docker log content.
  logs="$(timeout 8 docker logs --tail 40 "${name}" 2>&1)" || logs=''
  category=none_observed
  case "${name}" in
    prometheus)
      if [[ "${logs}" == *'permission denied'* && "${logs}" == *'rules'* ]]; then
        category=rule_read_permission
      elif [[ "${logs}" == *'permission denied'* ]]; then
        category=other_permission_denied
      elif [[ "${logs}" == *'Error loading config'* || "${logs}" == *'error parsing'* ]]; then
        category=config_parse_failure
      elif [[ "${logs}" == *'Error opening storage'* || "${logs}" == *'opening storage failed'* ]]; then
        category=storage_failure
      fi
      ;;
    pyroscope)
      if [[ "${logs}" == *'non-monotonic log entries'* ]]; then
        category=raft_non_monotonic
      elif [[ "${logs}" == *'permission denied'* ]]; then
        category=storage_permission_denied
      elif [[ "${logs}" == *'no space left on device'* ]]; then
        category=storage_full
      elif [[ "${logs}" == *'node is not the leader'* ]]; then
        category=raft_leader_unavailable
      elif [[ "${logs}" == *'no such file or directory'* ]]; then
        category=missing_path
      fi
      ;;
  esac
  printf '%s: recent_log_category=%s (last 40 lines; not a root-cause proof)\n' \
    "${name}" "${category}"

  curl_exit=0
  http_code="$(curl --silent --output /dev/null --connect-timeout 2 --max-time 6 \
    --write-out '%{http_code}' "${url}" 2>/dev/null)" || curl_exit="${?}"
  if [[ "${curl_exit}" == 0 && "${http_code}" == 200 ]]; then
    printf '%s: http=200 readiness=observed\n' "${name}"
  else
    printf '%s: http=%s curl_exit=%s readiness=unverified\n' \
      "${name}" "${http_code:-000}" "${curl_exit}"
    failures=$((failures + 1))
  fi
}

check_container prometheus http://172.17.0.24:9090/-/ready
check_container pyroscope http://172.17.0.24:4040/metrics
if (( failures > 0 )); then
  printf 'INCOMPLETE: %d service checks are not ready; no changes made\n' "${failures}"
  exit 1
fi
printf 'PASS: both HTTP checks returned 200; application health still needs review\n'
