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
CTEM_AMASS_ENABLED="${NABLA_CRON_CTEM_AMASS_ENABLED:-false}"
CTEM_WEB_ENABLED="${NABLA_CRON_CTEM_WEB_ENABLED:-false}"
CTEM_MAIL_ENABLED="${NABLA_CRON_CTEM_MAIL_ENABLED:-false}"
ZAP_PRIVATE_ENABLED="${NABLA_CRON_ZAP_PRIVATE_ENABLED:-false}"
ZAP_PRIVATE_ENGAGEMENT="${NABLA_CRON_ZAP_PRIVATE_ENGAGEMENT_ID:-}"
OPENTOFU_DRIFT_ENABLED="${NABLA_CRON_OPENTOFU_DRIFT_ENABLED:-true}"
CONVERGE_ENABLED="${NABLA_CRON_CONVERGE_ENABLED:-true}"
OPENTOFU_DRIFT_ALERTMANAGER_URL="${NABLA_CRON_OPENTOFU_DRIFT_ALERTMANAGER_URL:-http://172.17.0.24:9093}"
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

log_info "Hourly sync of ${REPO_DIR}: fast-forward to origin/${DEPLOY_BRANCH} (never reset), plan (never apply) the redeploy of TrueNAS Apps the new commits touch, reload Prometheus when its rules change, report TrueNAS Apps and containers started in the last ${RECENT_MINUTES} min, update FastAPI Sample only when ${FASTAPI_CLOUD_URL} is fully healthy."

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

# Converge a TrueNAS declaration every hour: idempotent, and it repairs UI edits.
# Hourly rather than on a diff: the first run after a merge still executes the
# sync_checkout bash loaded before the pull.
converge() {
  local script="$1" output changes
  [[ "${CONVERGE_ENABLED}" == true ]] || return 0
  if output="$(sudo -n python3 "${SCRIPT_DIR}/truenas/${script}" --apply 2>&1)"; then
    changes="$(grep -cE '^(CREATED|UPDATED|DELETED|SENT)' <<<"${output}" || true)"
    [[ "${changes}" == 0 ]] || log_info "${script}: ${changes} change(s) applied."
  else
    log_error "${script}: $(tail -n 1 <<<"${output}")"
    return 1
  fi
}

sync_checkout() {
  local local_sha remote_sha merge_output reload

  if ! git -c fetch.recurseSubmodules=false fetch origin "${DEPLOY_BRANCH}" 2>/dev/null; then
    log_error "git fetch origin ${DEPLOY_BRANCH} failed; checkout left unchanged."
    return 1
  fi
  local_sha="$(git rev-parse HEAD)"
  remote_sha="$(git rev-parse "origin/${DEPLOY_BRANCH}")"

  if [[ "${local_sha}" == "${remote_sha}" ]]; then
    log_info "Git: no new commit, checkout at ${local_sha:0:12}."
    # A manual pull skips the diff-based reload below; this is a no-op unless a
    # rule file is newer than Prometheus' last reload.
    reload="$(sudo -n bash "${SCRIPT_DIR}/truenas/reload-prometheus-rules.sh" apply 2>&1 | tail -n 1)"
    [[ "${reload}" == "OK: reload_needed=no"* ]] || log_info "Prometheus: ${reload}"
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
  # Exception to "plan only": a rule/config change needs a SIGHUP, not a redeploy, and an
  # invalid file is refused by promtool before any signal.
  if ! git diff --quiet "${local_sha}" HEAD -- apps/prometheus/prometheus.yml apps/prometheus/rules/; then
    log_info "Prometheus: $(sudo -n bash "${SCRIPT_DIR}/truenas/reload-prometheus-rules.sh" apply 2>&1 | tail -n 1)"
  fi
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
# Anonymous routes only: /readyz and /healthz need X-Diagnostics-Key since
# fastapi-sample #447, and the cron holds no FastAPI secret.
fastapi_cloud_unhealthy_reason() {
  local path code payload

  for path in livez v2/version; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "${FASTAPI_CLOUD_URL}/${path}" 2>/dev/null || true)"
    if [[ "${code}" != 200 ]]; then
      printf '/%s answered HTTP %s' "${path}" "${code:-none}"
      return 0
    fi
  done
  if ! payload="$(curl -fsS --max-time 20 "${FASTAPI_CLOUD_URL}/health" 2>/dev/null)"; then
    printf '/health unreachable'
    return 0
  fi
  if jq -e "${FASTAPI_HEALTHY_FILTER}" <<<"${payload}" >/dev/null 2>&1; then
    return 0
  fi
  jq -r '"status=\(.status // "unknown"), failing: " + ([.components // {} | to_entries[] | select(.value.status != "healthy") | .key] | join(", "))' <<<"${payload}" 2>/dev/null ||
    printf '/health payload is not JSON'
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

# Reuse this installed TrueNAS hourly Cron rather than creating a second job.
# Sunday 05:00 appliance local time only; the scan runner has its own flock.
# Failures are reported in the existing Cron mail but do not suppress Git sync.
run_weekly_ctem_amass() {
  local weekday hour rc=0
  if [[ "${CTEM_AMASS_ENABLED}" != true ]]; then
    return 0
  fi
  weekday="$(date +%u)"
  hour="$(date +%H)"
  if [[ "${weekday}" != 7 || "${hour}" != 05 ]]; then
    return 0
  fi
  if [[ ! -f "${SCRIPT_DIR}/security/run-ctem-amass-truenas.sh" ]]; then
    log_error "CTEM: runner not installed in checkout"
    return 1
  fi
  log_info "CTEM: running approved bounded active weekly Amass; private candidates stay on TrueNAS."
  local web_approved=NO
  [[ "${CTEM_WEB_ENABLED}" == true ]] && web_approved=YES
  sudo -n env CTEM_AMASS_ACTIVE_APPROVED=YES CTEM_REPORT_STORE_APPROVED=YES \
    CTEM_WEB_PUBLISH_APPROVED="${web_approved}" \
    bash "${SCRIPT_DIR}/security/run-ctem-amass-truenas.sh" --run || rc=$?
  if ((rc == 0)); then
    log_info "CTEM: completed, private artifact retained; only counts may be published."
  else
    log_error "CTEM: incomplete, exit=${rc}; no finding promotion."
  fi
  return "${rc}"
}

# The existing GitHub App artifact collector already has Actions:read on
# nabla-compose. Fetch only the latest successful master mail-deep artifact;
# no API token is forwarded to artifact storage, no DefectDojo import here.
run_weekly_ctem_mail() {
  local weekday hour rc=0
  if [[ "${CTEM_MAIL_ENABLED}" != true ]]; then
    return 0
  fi
  weekday="$(date +%u)"
  hour="$(date +%H)"
  if [[ "${weekday}" != 1 || "${hour}" != 08 ]]; then
    return 0
  fi
  if [[ ! -f "${SCRIPT_DIR}/security/pull-ctem-mail-artifact.py" ]]; then
    log_error "CTEM mail: GitHub artifact puller not installed"
    return 1
  fi
  log_info "CTEM mail: collecting reviewed master JSON posture via GitHub App Actions:read."
  sudo -n env CTEM_MAIL_PULL_APPROVED=YES CTEM_REPORT_STORE_APPROVED=YES \
    python3 "${SCRIPT_DIR}/security/pull-ctem-mail-artifact.py" --store || rc=$?
  if ((rc == 0)); then
    log_info "CTEM mail: sanitized checkdmarc receipt stored in shared PostgreSQL."
  else
    log_error "CTEM mail: incomplete, exit=${rc}; no DefectDojo auto import."
  fi
  return "${rc}"
}

# Reuse the already-installed TrueNAS hourly Cron: Saturday 06:00 local time.
# Preserve raw XML/JSON/HTML/Markdown regardless of import result.
run_weekly_private_zap() {
  local weekday hour rc=0
  [[ "${ZAP_PRIVATE_ENABLED}" == true ]] || return 0
  weekday="$(date +%u)"
  hour="$(date +%H)"
  [[ "${weekday}" == 6 && "${hour}" == 06 ]] || return 0
  if [[ ! "${ZAP_PRIVATE_ENGAGEMENT}" =~ ^[1-9][0-9]*$ ]]; then
    log_error "Site Alban ZAP: set NABLA_CRON_ZAP_PRIVATE_ENGAGEMENT_ID to an existing DefectDojo engagement"
    return 1
  fi
  log_info "Site Alban ZAP: full private scan, archive and DefectDojo native XML import."
  sudo -n env NABLA_ZAP_PRIVATE_SCAN_APPROVED=YES \
    NABLA_ZAP_PRIVATE_AUTO_IMPORT=YES \
    DEFECTDOJO_ENGAGEMENT_ID="${ZAP_PRIVATE_ENGAGEMENT}" \
    NABLA_ZAP_VERCEL_BYPASS_FILE="${NABLA_ZAP_VERCEL_BYPASS_FILE:-}" \
    python3 "${SCRIPT_DIR}/security/run-site-alban-zap-private.py" --run || rc=$?
  if ((rc != 0)); then
    log_error "Site Alban ZAP: scan/import incomplete (exit ${rc}); full archive retained on TrueNAS"
  else
    log_info "Site Alban ZAP: completed; inspect private manifest and DefectDojo receipt"
  fi
  return "${rc}"
}

# Daily 09:00 (after the 01-07 night window) read-only OpenTofu plan of
# origin/master against production; never apply. Roots without their
# credentials file are SKIPPED. See docs/infrastructure-bootstrap.md.
run_daily_opentofu_drift() {
  local tools rc=0
  if [[ "${OPENTOFU_DRIFT_ENABLED}" != true || "$(date +%H)" != 09 ]]; then
    return 0
  fi
  # Same pins as .github/workflows/terragrunt-ci.yaml, resolved by this user's
  # mise; the plan runs as root to read the root-only 0600 credentials.
  # shellcheck disable=SC2016 # expanded by the inner sh, inside mise's PATH
  tools="$("${HOME}/.local/bin/mise" exec opentofu@1.12.5 terragrunt@0.97.0 -- \
    sh -c 'echo "$(dirname "$(command -v tofu)"):$(dirname "$(command -v terragrunt)")"')" || {
    log_error "OpenTofu drift: mise cannot provide opentofu@1.12.5 and terragrunt@0.97.0"
    return 1
  }
  sudo -n env PATH="${tools}:/usr/bin:/bin" python3 "${SCRIPT_DIR}/infra/opentofu-drift-check.py" \
    --run --alertmanager-url "${OPENTOFU_DRIFT_ALERTMANAGER_URL}" || rc=$?
  case "${rc}" in
    0) log_info "OpenTofu drift: in sync (or roots not enrolled yet)." ;;
    2) log_error "OpenTofu drift: master differs from production; OpenTofuDrift alert raised." ;;
    *) log_error "OpenTofu drift: check incomplete, exit=${rc}." ;;
  esac
  return "${rc}"
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
  # Second exception to "plan only", after the Prometheus reload.
  converge reconcile-mail-settings.py || status=1
  converge reconcile-cron-jobs.py || status=1
  run_weekly_ctem_amass || status=1
  run_weekly_ctem_mail || status=1
  run_weekly_private_zap || status=1
  run_daily_opentofu_drift || status=1
  update_fastapi_sample || status=1
fi
exit "${status}"
