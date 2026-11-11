#!/usr/bin/env bash
# Prepared, one-App-at-a-time rollout of the TrueNAS Apps that the catalog
# declares but that are not deployed yet (runbook 2026-11-04 §5).
#
#   bash scripts/truenas/rollout-pending-apps.sh --plan [app]          # no root: ordered steps
#   sudo bash scripts/truenas/rollout-pending-apps.sh --check [app]    # read-only preflight of every gate
#   sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/rollout-pending-apps.sh --apply <app>
#
# --check calls only the --check modes of the existing bootstrap/deploy scripts
# and reads middleware state; it reports every gate instead of stopping at the
# first failure. --apply deploys exactly one App through its owning deployer,
# then re-applies the backup role so the new database is covered by
# apps/postgresbackup. Nothing here starts a Compose project directly.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

MODE="${1:---plan}"
TARGET="${2:-all}"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
# Prepared order: shared data consumers first, ntopng last (host network).
ORDER=(netbox dependency-track plumber scanopy joplin ntopng)

usage() {
  printf 'usage: %s [--plan|--check|--apply] [%s|all]\n' "$0" "$(
    IFS='|'
    printf '%s' "${ORDER[*]}"
  )" >&2
  exit 2
}

case "${MODE}" in
--plan | --check | --apply) ;;
*) usage ;;
esac

app_known() {
  local app
  for app in "${ORDER[@]}"; do
    [[ "$1" == "${app}" ]] && return 0
  done
  return 1
}
if [[ "${TARGET}" != "all" ]]; then
  app_known "${TARGET}" || fail "unsupported app: ${TARGET} (order: ${ORDER[*]})"
  SELECTED=("${TARGET}")
else
  SELECTED=("${ORDER[@]}")
fi
if [[ "${MODE}" == "--apply" ]]; then
  [[ "${TARGET}" != "all" ]] || fail "--apply is deliberately one App at a time: name the App"
  [[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
    fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check"
fi

# ---------------------------------------------------------------------------
# Single source of truth for the steps. Lines: phase|name|command.
# phase: check (read-only), apply (mutation through the owning deployer),
# post (after a successful apply). Commands are fixed strings; the only
# variable part is the App id validated against ORDER above.
# ---------------------------------------------------------------------------
app_database() {
  case "$1" in
  netbox) printf 'netbox\n' ;;
  dependency-track) printf 'dependencytrack\n' ;;
  plumber) printf 'jobs\n' ;;
  scanopy | joplin) printf '%s\n' "$1" ;;
  *) printf '\n' ;;
  esac
}

app_prerequisites() {
  case "$1" in
  netbox | plumber) printf 'postgres redis\n' ;;
  dependency-track | scanopy | joplin) printf 'postgres\n' ;;
  esac
}

app_prometheus_job() {
  case "$1" in
  netbox) printf 'netbox\n' ;;
  dependency-track) printf 'dependency_track\n' ;;
  *) printf '\n' ;;
  esac
}

app_steps() {
  local app="$1"
  case "${app}" in
  netbox | dependency-track | plumber)
    printf '%s\n' \
      "check|secrets|bash scripts/truenas/prepare-security-tooling-secrets.sh --check ${app}" \
      "check|storage|bash scripts/truenas/bootstrap-repository-storage.sh --check ${app}" \
      "check|postgres|bash scripts/truenas/bootstrap-app-postgres.sh --check ${app}" \
      "check|compose|docker compose -f apps/${app}/compose.yml config --quiet --no-interpolate --no-env-resolution" \
      "apply|deploy|bash scripts/truenas/deploy-security-tooling.sh --apply ${app}"
    ;;
  scanopy | joplin)
    printf '%s\n' \
      "check|deploy-preflight|bash scripts/truenas/deploy-${app}.sh --check" \
      "apply|postgres|bash scripts/truenas/bootstrap-app-postgres.sh --apply ${app}" \
      "apply|deploy|bash scripts/truenas/deploy-${app}.sh --apply"
    ;;
  ntopng)
    printf '%s\n' \
      "check|storage|bash scripts/truenas/bootstrap-repository-storage.sh --check ntopng" \
      "check|deploy-preflight|bash scripts/truenas/deploy-ntopng.sh --check" \
      "apply|deploy|bash scripts/truenas/deploy-ntopng.sh --apply"
    ;;
  esac
  [[ -z "$(app_database "${app}")" ]] ||
    printf '%s\n' "post|backup-role|bash scripts/truenas/bootstrap-postgresbackup-role.sh --apply"
}

app_acceptance() {
  local app="$1" job
  printf 'app.query %s state=RUNNING; Gatus monitor %s green; /api/homelab/status %s=in_sync' "${app}" "${app}" "${app}"
  job="$(app_prometheus_job "${app}")"
  [[ -z "${job}" ]] || printf '; up{job="%s"}=1' "${job}"
  printf '\n'
}

# ---------------------------------------------------------------------------
# --plan: documentation as code, no root, no middleware access.
# ---------------------------------------------------------------------------
if [[ "${MODE}" == "--plan" ]]; then
  position=0
  for app in "${SELECTED[@]}"; do
    position=$((position + 1))
    printf 'plan app=%s order=%s database=%s prerequisites=%s\n' \
      "${app}" "${position}" "$(app_database "${app}")" "$(app_prerequisites "${app}" | tr ' ' ',')"
    while IFS='|' read -r phase name command; do
      printf 'plan app=%s %s %s: %s\n' "${app}" "${phase}" "${name}" "${command}"
    done < <(app_steps "${app}")
    [[ "${app}" != "ntopng" ]] ||
      printf 'plan app=ntopng note: Community edition, capture interface from apps/ntopng/ntopng.conf; admin password from nabla/prod/ntopng\n'
    printf 'plan app=%s acceptance: %s\n' "${app}" "$(app_acceptance "${app}")"
  done
  exit 0
fi

# ---------------------------------------------------------------------------
# --check / --apply: TrueNAS canonical checkout required.
# ---------------------------------------------------------------------------
require_root "run with sudo on TrueNAS"
require_commands docker git jq midclt python3
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT:-<none>}"
cd "${CANONICAL_ROOT}"
truenas_repo_provenance "${CANONICAL_ROOT}"

LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/nabla-rollout.XXXXXX")"
chmod 0700 "${LOG_DIR}"
blocked=0
ready=0

# Run one step; the complete output goes to a private log, the report line
# stays bounded. Returns the step's exit status.
run_step() {
  local app="$1" name="$2" command="$3" log rc
  log="${LOG_DIR}/${app}-${name}.log"
  if bash -c "${command}" >"${log}" 2>&1; then
    printf 'rollout app=%s step=%s result=OK\n' "${app}" "${name}"
    return 0
  else
    # Capture status in the else branch: after a failed 'if' without 'else',
    # $? is zero and can falsely report success.
    rc=$?
  fi
  # Child output is private. Never forward it to the operator/CI summary:
  # even the last line may contain a credential or a database URL.
  printf 'rollout app=%s step=%s result=BLOCKED exit=%s log=private\n' \
    "${app}" "${name}" "${rc}"
  return "${rc}"
}

check_prerequisites() {
  local app="$1" dependency state status=0
  for dependency in $(app_prerequisites "${app}"); do
    state="$(truenas_app_state "${dependency}")"
    if [[ "${state}" == "RUNNING" ]]; then
      printf 'rollout app=%s prerequisite=%s state=%s result=OK\n' "${app}" "${dependency}" "${state}"
    else
      printf 'rollout app=%s prerequisite=%s state=%s result=BLOCKED\n' "${app}" "${dependency}" "${state}"
      status=1
    fi
  done
  return "${status}"
}

run_phase() {
  local app="$1" wanted="$2" stop_on_failure="$3" phase name command status=0
  while IFS='|' read -r phase name command; do
    [[ "${phase}" == "${wanted}" ]] || continue
    if ! run_step "${app}" "${name}" "${command}"; then
      status=1
      [[ "${stop_on_failure}" == "no" ]] || return 1
    fi
  done < <(app_steps "${app}")
  return "${status}"
}

if [[ "${MODE}" == "--check" ]]; then
  section "Pending Apps preflight (read-only) · logs ${LOG_DIR}"
  for app in "${SELECTED[@]}"; do
    app_status=0
    printf 'rollout app=%s middleware_state=%s\n' "${app}" "$(truenas_app_state "${app}")"
    check_prerequisites "${app}" || app_status=1
    run_phase "${app}" check no || app_status=1
    if ((app_status == 0)); then
      ready=$((ready + 1))
      printf 'rollout app=%s verdict=READY next=%s\n' "${app}" \
        "sudo NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/rollout-pending-apps.sh --apply ${app}"
    else
      blocked=$((blocked + 1))
      printf 'rollout app=%s verdict=BLOCKED\n' "${app}"
    fi
  done
  # The backup role is informative here: it is re-applied after every deploy.
  run_step backup role-check "bash scripts/truenas/bootstrap-postgresbackup-role.sh --check" || true
  printf 'rollout_summary mode=check ready=%s blocked=%s mutations=0\n' "${ready}" "${blocked}"
  ((blocked == 0))
  exit $?
fi

# --apply: exactly one App, prerequisites first, owning deployer, then the backup role.
app="${SELECTED[0]}"
section "Rollout --apply ${app} · logs ${LOG_DIR}"
check_prerequisites "${app}" || fail "${app}: shared data prerequisites are not RUNNING"
run_phase "${app}" apply yes || fail "${app}: deployment stopped at the first failing step (logs: ${LOG_DIR})"
run_phase "${app}" post yes || fail "${app}: post-deployment step failed (logs: ${LOG_DIR})"
truenas_app_summary "${app}"
printf 'rollout app=%s acceptance: %s\n' "${app}" "$(app_acceptance "${app}")"
printf 'rollout_summary mode=apply app=%s result=deployed runtime_acceptance=NOT_VERIFIED\n' "${app}"
