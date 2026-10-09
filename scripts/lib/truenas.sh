# shellcheck shell=bash
# Shared read-only TrueNAS middleware/lifecycle helpers.
#
# This file is sourced by operator scripts. Keep diagnostics bounded and never
# emit environment values or Compose payloads that may contain secrets.

truenas_lifecycle_mark() {
  local log_path="${TRUENAS_APP_LIFECYCLE_LOG:-/var/log/app_lifecycle.log}"

  if [[ ! -r "${log_path}" ]]; then
    printf '0\n'
    return 0
  fi

  wc -l <"${log_path}" | tr -d '[:space:]'
  printf '\n'
}

truenas_lifecycle_errors_since() {
  local app_id="${1:?TrueNAS app id is required}"
  local mark="${2:-0}"
  local limit="${3:-40}"
  local log_path="${TRUENAS_APP_LIFECYCLE_LOG:-/var/log/app_lifecycle.log}"
  local current_lines start_line evidence

  [[ "${mark}" =~ ^[0-9]+$ ]] || mark=0
  [[ "${limit}" =~ ^[1-9][0-9]*$ ]] || limit=40

  if [[ ! -r "${log_path}" ]]; then
    printf 'INFO: TrueNAS lifecycle log is not readable: %s\n' "${log_path}" >&2
    return 0
  fi

  current_lines="$(wc -l <"${log_path}" | tr -d '[:space:]')"
  [[ "${current_lines}" =~ ^[0-9]+$ ]] || current_lines=0

  # Log rotation/truncation can make a pre-mutation line mark larger than the
  # current file. In that case inspect the current file rather than silently
  # missing fresh evidence.
  if ((mark > current_lines)); then
    mark=0
  fi
  start_line=$((mark + 1))

  evidence="$({
    tail -n "+${start_line}" "${log_path}" 2>/dev/null || true
  } | grep -F "${app_id}" |
    grep -Ei 'error|fail(ed|ure)?|exception|traceback|critical|unable|cannot|tim(e|ed)[ -]?out' |
    tail -n "${limit}" || true)"

  if [[ -z "${evidence}" ]]; then
    printf 'OK: no new TrueNAS lifecycle error evidence for %s\n' "${app_id}"
    return 0
  fi

  printf 'WARNING: new TrueNAS lifecycle error evidence for %s (max %s lines):\n' \
    "${app_id}" "${limit}" >&2
  printf '%s\n' "${evidence}" >&2
  return 1
}

truenas_app_query_by_id() {
  local app_id="${1:?TrueNAS app id is required}"
  midclt call app.query "[[\"id\",\"=\",\"${app_id}\"]]"
}

truenas_app_state() {
  local app_id="${1:?TrueNAS app id is required}"
  truenas_app_query_by_id "${app_id}" |
    jq -r 'if length == 1 then .[0].state else "MISSING" end'
}

truenas_repo_provenance() {
  local repo_root="${1:-.}"
  local head upstream dirty relation counts left right

  head="$(git -C "${repo_root}" rev-parse --short=12 HEAD 2>/dev/null || printf 'unknown')"
  if [[ -n "$(git -C "${repo_root}" status --porcelain 2>/dev/null || true)" ]]; then
    dirty="dirty"
  else
    dirty="clean"
  fi

  upstream="$(git -C "${repo_root}" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  relation="no-upstream"
  if [[ -n "${upstream}" ]]; then
    counts="$(git -C "${repo_root}" rev-list --left-right --count "HEAD...${upstream}" 2>/dev/null || true)"
    left="${counts%%[[:space:]]*}"
    right="${counts##*[[:space:]]}"
    if [[ "${left}" =~ ^[0-9]+$ && "${right}" =~ ^[0-9]+$ ]]; then
      case "${left}:${right}" in
        0:0) relation="synced" ;;
        0:*) relation="behind-${right}" ;;
        *:0) relation="ahead-${left}" ;;
        *) relation="diverged-${left}-${right}" ;;
      esac
    fi
  fi

  printf 'INFO: repository head=%s tree=%s upstream=%s relation=%s\n' \
    "${head}" "${dirty}" "${upstream:-none}" "${relation}" >&2
}

truenas_job_compact() {
  local method="${1:?TrueNAS middleware job method is required}"
  shift
  local tail_lines="${TRUENAS_JOB_LOG_TAIL:-40}"
  local verbose="${TRUENAS_DEPLOY_VERBOSE:-false}"
  local tmp rc
  local -a job_cmd=(midclt call -j)

  [[ "${tail_lines}" =~ ^[1-9][0-9]*$ ]] || tail_lines=40
  if ((EUID != 0)) && command -v sudo >/dev/null 2>&1; then
    job_cmd=(sudo midclt call -j)
  fi

  case "${verbose}" in
    1 | true | TRUE | yes | YES)
      "${job_cmd[@]}" "${method}" "$@"
      return
      ;;
  esac

  tmp="$(mktemp "${TMPDIR:-/tmp}/nabla-truenas-job.XXXXXX")"
  if "${job_cmd[@]}" "${method}" "$@" >"${tmp}" 2>&1; then
    rm -f "${tmp}"
    printf 'OK: TrueNAS job %s completed\n' "${method}"
    return 0
  else
    rc=$?
  fi
  printf 'ERROR: TrueNAS job %s failed (exit=%s); last %s lines follow\n' \
    "${method}" "${rc}" "${tail_lines}" >&2
  tr '\r' '\n' <"${tmp}" | tail -n "${tail_lines}" >&2 || true
  rm -f "${tmp}"
  return "${rc}"
}

truenas_compose_container_id() {
  local app_id="${1:?TrueNAS app id is required}"
  local service="${2:?Compose service name is required}"
  local container_id

  container_id="$(
    docker ps -aq \
      --filter "label=com.docker.compose.project=ix-${app_id}" \
      --filter "label=com.docker.compose.service=${service}" |
      head -n 1
  )"

  if [[ -z "${container_id}" ]]; then
    container_id="$(
      docker ps -aq --filter "name=^ix-${app_id}-${service}-1$" |
        head -n 1
    )"
  fi

  printf '%s\n' "${container_id}"
}

truenas_app_summary() {
  local app_id="${1:?TrueNAS app id is required}"

  truenas_app_query_by_id "${app_id}" |
    jq -r '
      if length == 1 then
        .[0]
        | "OK: TrueNAS app \(.id) state=\(.state // \"UNKNOWN\") containers=\(.active_workloads.containers // 0)"
      else
        "WARNING: TrueNAS app not found: '"${app_id}"'"
      end
    '
}

truenas_reconcile_custom_app() {
  local app_id="${1:?TrueNAS app id is required}"
  local compose_path="${2:?compose path is required}"
  local payload wrapper

  [[ -f "${compose_path}" ]] || {
    printf 'ERROR: missing Compose file: %s\n' "${compose_path}" >&2
    return 1
  }

  if truenas_app_query_by_id "${app_id}" |
    jq -e 'length == 1' >/dev/null; then
    payload="$(jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {include: [$include]}
    }')"
    truenas_job_compact app.update "${app_id}" "${payload}"
  else
    wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
    payload="$(jq -cn --arg app_name "${app_id}" --arg compose "${wrapper}" '{
      app_name: $app_name,
      custom_app: true,
      custom_compose_config_string: $compose
    }')"
    truenas_job_compact app.create "${payload}"
  fi
}

truenas_wait_app_running() {
  local app_id="${1:?TrueNAS app id is required}"
  local timeout_seconds="${2:-600}"
  local poll_seconds="${3:-4}"
  local deadline state
  deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    state="$(truenas_app_state "${app_id}")"
    case "${state}" in
      RUNNING) return 0 ;;
      CRASHED | ERROR | MISSING)
        printf 'ERROR: %s converged to %s\n' "${app_id}" "${state}" >&2
        return 1
        ;;
    esac
    sleep "${poll_seconds}"
  done
  printf 'ERROR: %s did not reach RUNNING within %ss (state=%s)\n' \
    "${app_id}" "${timeout_seconds}" "$(truenas_app_state "${app_id}")" >&2
  return 1
}

truenas_dataset_query_by_id() {
  local dataset_id="${1:?TrueNAS dataset id is required}"
  midclt call pool.dataset.query "[[\"id\",\"=\",\"${dataset_id}\"]]"
}

truenas_nfs_share_count_for_path() {
  local share_path="${1:?TrueNAS NFS share path is required}"
  midclt call sharing.nfs.query |
    jq --arg path "${share_path}" '
      [
        .[]
        | select(
            (.path? == $path)
            or (((.paths? // []) | index($path)) != null)
          )
      ]
      | length
    '
}

truenas_docker_status() {
  midclt call docker.status 2>/dev/null |
    jq -r '.status // "UNKNOWN"'
}
