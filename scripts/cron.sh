#!/usr/bin/env bash
# Hourly TrueNAS cron: fast-forward the deployment checkout, report runtime
# state, and refresh FastAPI Sample once FastAPI Cloud proves it healthy.
set -euo pipefail

if [[ -z "${1:-}" ]]; then
  echo "Usage: $0 <repo-dir>" >&2
  exit 1
fi

REPO_DIR="$1"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_BRANCH="${NABLA_CRON_BRANCH:-master}"
LOCK_FILE="${NABLA_CRON_LOCK_FILE:-/tmp/nabla-compose-doco-cd-update.lock}"
LOG_TAG="doco-cd-update"
RECENT_MINUTES="${NABLA_CRON_RECENT_MINUTES:-65}"
DOCO_CD_PROJECTS="${NABLA_CRON_DOCO_CD_PROJECTS:-vaultwarden garage}"
FASTAPI_UPDATE="${NABLA_CRON_FASTAPI_UPDATE:-true}"
FASTAPI_CLOUD_URL="${NABLA_CRON_FASTAPI_CLOUD_URL:-https://fastapi-sample.fastapicloud.dev}"
FASTAPI_REMOTE="${NABLA_CRON_FASTAPI_REMOTE:-https://github.com/AlbanAndrieu/fastapi-sample.git}"
FASTAPI_SUBMODULE="${FASTAPI_SAMPLE_SUBMODULE:-apps/fastapi-sample}"
FASTAPI_TIMEOUT="${NABLA_CRON_FASTAPI_TIMEOUT:-50m}"
OPS_LOG_DIR="${NABLA_CRON_LOG_DIR:-/mnt/cpool/var/nabla/ops-logs}"
# Fully healthy = top-level status and every component healthy, as update-fastapi-sample.sh requires locally.
FASTAPI_HEALTHY_FILTER='.status == "healthy" and ([.components[]?.status] | length > 0 and all(. == "healthy"))'

log_info() {
  echo "[${LOG_TAG}] $*"
  logger -t "${LOG_TAG}" "$*"
}

log_error() {
  echo "[${LOG_TAG}] ERROR: $*" >&2
  logger -s -t "${LOG_TAG}" "ERROR: $*"
}

for command in git logger flock; do
  command -v "${command}" >/dev/null 2>&1 || {
    log_error "${command} is required"
    exit 1
  }
done

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log_info "Another cron/bootstrap reconciliation is already running; skipping."
  exit 0
fi

log_info "Hourly sync of ${REPO_DIR}: fast-forward to origin/${DEPLOY_BRANCH} (never reset), plan (never apply) the redeploy of TrueNAS Apps the new commits touch, report TrueNAS Apps and containers started in the last ${RECENT_MINUTES} min, update FastAPI Sample only when ${FASTAPI_CLOUD_URL} is fully healthy."

cd "${REPO_DIR}"

CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "${CURRENT_BRANCH}" != "${DEPLOY_BRANCH}" ]]; then
  log_info "Checkout is on ${CURRENT_BRANCH:-detached}, not ${DEPLOY_BRANCH}; skipping local self-update. Doco-CD remote polling remains independent."
  exit 0
fi

# Protect tracked superproject edits. Dirty/unpinned submodule working trees are
# deliberately ignored here: cron owns the deployment checkout metadata, not
# developer changes inside submodule directories.
if ! git diff --quiet --ignore-submodules=all ||
  ! git diff --cached --quiet --ignore-submodules=all; then
  log_error "Tracked superproject changes are present; refusing automatic update."
  exit 1
fi

DOCKER=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
  fi
fi

sync_checkout() {
  local local_sha remote_sha merge_output

  if ! git -c fetch.recurseSubmodules=false fetch origin "${DEPLOY_BRANCH}" 2>/dev/null; then
    log_error "git fetch origin ${DEPLOY_BRANCH} failed; checkout left unchanged."
    return 1
  fi
  local_sha="$(git rev-parse HEAD)"
  remote_sha="$(git rev-parse "origin/${DEPLOY_BRANCH}")"

  if [[ "${local_sha}" == "${remote_sha}" ]]; then
    log_info "Git: no new commit, checkout at ${local_sha:0:12}."
    return 0
  fi

  if ! git merge-base --is-ancestor "${local_sha}" "${remote_sha}"; then
    log_error "Local ${DEPLOY_BRANCH} is not a fast-forward ancestor of origin/${DEPLOY_BRANCH}; refusing destructive reset."
    return 1
  fi

  # Captured so the cron mail shows a summary instead of git's progress lines.
  if ! merge_output="$(git -c submodule.recurse=false merge --ff-only "origin/${DEPLOY_BRANCH}" 2>&1)"; then
    log_error "Fast-forward failed: $(tail -n 3 <<<"${merge_output}" | tr '\r\n' '  ')"
    return 1
  fi

  log_info "Git: ${local_sha:0:12} -> ${remote_sha:0:12}, $(git rev-list --count "${local_sha}..HEAD") new commit(s):"
  git log --oneline --no-decorate -10 "${local_sha}..HEAD" | sed 's/^/  /'
  # Plan only: redeploying Apps waits for the operator's --apply.
  python3 "${SCRIPT_DIR}/truenas/redeploy-impacted-apps.py" --from "${local_sha}" --to HEAD 2>&1 ||
    log_info "Impacted TrueNAS Apps: plan incomplete, nothing redeployed."

  if git diff --quiet "${local_sha}" HEAD -- bootstrap/ docker-compose-truenas.yml .doco-cd.yaml; then
    log_info "Checkout synchronized; no Doco-CD configuration changed."
  else
    log_info "Doco-CD configuration changed in the synchronized checkout."
  fi
  log_info "Git synchronization complete. Runtime deployment remains owned by the already-running Doco-CD instance; cron never starts/replaces doco-cd."
}

query_apps() {
  local query='{"select":["id","state"]}'
  timeout 60 midclt call app.query '[]' "${query}" 2>/dev/null ||
    timeout 60 sudo -n midclt call app.query '[]' "${query}" 2>/dev/null
}

report_apps() {
  local payload

  if ! command -v midclt >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1 ||
    ! payload="$(query_apps)"; then
    log_info "TrueNAS Apps: state unavailable (midclt app.query failed or timed out)."
    return 0
  fi
  log_info "TrueNAS Apps: $(jq -r 'group_by(.state) | map("\(.[0].state)=\(length)") | join(", ")' <<<"${payload}")"
  log_info "Apps not RUNNING: $(jq -r '[.[] | select(.state != "RUNNING") | "\(.id) (\(.state))"] | join(", ") | if . == "" then "none" else . end' <<<"${payload}")"
}

report_recent_containers() {
  local cutoff ids name project started restarts started_at owner count=0

  if ((${#DOCKER[@]} == 0)); then
    log_info "Containers: docker unavailable (user not in the docker group and sudo -n refused)."
    return 0
  fi
  mapfile -t ids < <("${DOCKER[@]}" ps -q)
  log_info "Containers running: ${#ids[@]}. Started in the last ${RECENT_MINUTES} min:"
  ((${#ids[@]} > 0)) || return 0

  cutoff=$(($(date +%s) - RECENT_MINUTES * 60))
  while IFS='|' read -r name project started restarts; do
    started_at="$(date -d "${started}" +%s 2>/dev/null)" || continue
    ((started_at >= cutoff)) || continue
    case "${project}" in
      ix-*) owner="TrueNAS App ${project#ix-}" ;;
      "") owner="standalone container" ;;
      *)
        if [[ " ${DOCO_CD_PROJECTS} " == *" ${project} "* ]]; then
          owner="Doco-CD ${project}"
        else
          owner="Compose project ${project}"
        fi
        ;;
    esac
    printf '  %s: %s, started %s, restarts=%s\n' "${name#/}" "${owner}" "$(date -d "${started}" '+%H:%M')" "${restarts}"
    count=$((count + 1))
  done < <("${DOCKER[@]}" inspect --format '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.State.StartedAt}}|{{.RestartCount}}' "${ids[@]}")
  ((count > 0)) || echo "  none"
}

# Prints why FastAPI Cloud is not fully healthy; succeeds silently when it is.
fastapi_cloud_unhealthy_reason() {
  local path code payload

  for path in livez readyz; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "${FASTAPI_CLOUD_URL}/${path}" 2>/dev/null || true)"
    if [[ "${code}" != 200 ]]; then
      printf '/%s answered HTTP %s' "${path}" "${code:-none}"
      return 0
    fi
  done
  if ! payload="$(curl -fsS --max-time 20 "${FASTAPI_CLOUD_URL}/healthz" 2>/dev/null)"; then
    printf '/healthz unreachable'
    return 0
  fi
  if jq -e "${FASTAPI_HEALTHY_FILTER}" <<<"${payload}" >/dev/null 2>&1; then
    return 0
  fi
  jq -r '"status=\(.status // "unknown"), failing: " + ([(.components // {} | to_entries[] | select(.value.status != "healthy") | .key), (.checks // {} | to_entries[] | select(.value.reachable == false) | .key)] | join(", "))' <<<"${payload}" 2>/dev/null ||
    printf '/healthz payload is not JSON'
}

update_fastapi_sample() {
  local current target reason log_dir log rc

  if [[ "${FASTAPI_UPDATE}" != true ]]; then
    log_info "FastAPI Sample: automatic update disabled (NABLA_CRON_FASTAPI_UPDATE=${FASTAPI_UPDATE})."
    return 0
  fi
  for command in curl jq timeout; do
    command -v "${command}" >/dev/null 2>&1 || {
      log_info "FastAPI Sample: ${command} missing; update skipped."
      return 0
    }
  done
  # An uninitialized submodule would make git -C resolve to the superproject.
  if [[ ! -e "${FASTAPI_SUBMODULE}/.git" ]]; then
    log_info "FastAPI Sample: submodule ${FASTAPI_SUBMODULE} not initialized; update skipped."
    return 0
  fi

  current="$(git -C "${FASTAPI_SUBMODULE}" rev-parse HEAD)"
  target="$(timeout 30 git ls-remote "${FASTAPI_REMOTE}" refs/heads/master 2>/dev/null | cut -f1 || true)"
  if [[ -z "${target}" ]]; then
    log_info "FastAPI Sample: cannot read master from ${FASTAPI_REMOTE}; update skipped."
    return 0
  fi
  if [[ "${current}" == "${target}" ]]; then
    log_info "FastAPI Sample: up to date at ${current:0:12}."
    return 0
  fi

  reason="$(fastapi_cloud_unhealthy_reason)"
  if [[ -n "${reason}" ]]; then
    log_info "FastAPI Sample: ${current:0:12} -> ${target:0:12} available, but FastAPI Cloud is not fully healthy (${reason}); update skipped."
    return 0
  fi

  log_dir="${OPS_LOG_DIR}"
  if ! mkdir -p "${log_dir}" 2>/dev/null || [[ ! -w "${log_dir}" ]]; then
    log_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/nabla/cron"
    mkdir -p "${log_dir}"
  fi
  log="${log_dir}/fastapi-sample-update-$(date -u +%Y%m%dT%H%M%SZ).log"
  log_info "FastAPI Sample: ${current:0:12} -> ${target:0:12}, FastAPI Cloud fully healthy; running update-fastapi-sample.sh (log ${log})."

  rc=0
  (umask 077 && timeout "${FASTAPI_TIMEOUT}" sudo -n bash scripts/truenas/update-fastapi-sample.sh >"${log}" 2>&1) || rc=$?
  if ((rc == 0)); then
    log_info "FastAPI Sample: update succeeded at $(git -C "${FASTAPI_SUBMODULE}" rev-parse --short=12 HEAD)."
    tail -n 8 "${log}" | sed 's/^/  /'
    return 0
  fi
  log_error "FastAPI Sample: update failed (exit ${rc}); last lines of ${log}:"
  tail -n 20 "${log}" | sed 's/^/  /' >&2
  return 1
}

status=0
synced=true
sync_checkout || {
  status=1
  synced=false
}
report_apps
report_recent_containers
if [[ "${synced}" == true ]]; then
  update_fastapi_sample || status=1
fi
exit "${status}"
