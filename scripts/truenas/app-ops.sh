#!/usr/bin/env bash
# One entry point per repository TrueNAS App for production operations:
#   status | storage | secrets | deploy | restart | diagnose | monitor | backup
# It dispatches to the existing, tested tools and adds no new mutation logic.
# Every action is read-only unless --apply is given; --apply also needs
# NABLA_RUNTIME_CHANGE_APPROVED=yes. The App facts (datasets, deployment path,
# databases, probes) come from scripts/truenas/audit-production-readiness.py.
# Runbook: docs/runbooks/production-app-operations.md
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

ACTIONS="status storage secrets deploy restart diagnose monitor backup"

usage() {
  printf 'usage: app-ops.sh <action> <app> [--apply]\nactions: %s\n' "${ACTIONS}" >&2
  exit 2
}

[[ "$#" -ge 2 && "$#" -le 3 ]] || usage
ACTION="$1"
APP_ID="$2"
APPLY=false
if [[ "$#" -eq 3 ]]; then
  [[ "$3" == "--apply" ]] || usage
  APPLY=true
fi
[[ " ${ACTIONS} " == *" ${ACTION} "* ]] || usage
[[ "${APP_ID}" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || fail "invalid app id: ${APP_ID}"
[[ -f "${REPO_ROOT}/apps/${APP_ID}/compose.yml" ]] || fail "apps/${APP_ID}/compose.yml is absent"
cd "${REPO_ROOT}"

ROW="$(python3 scripts/truenas/audit-production-readiness.py --app "${APP_ID}")"
field() { jq -r "$1" <<<"${ROW}"; }

# Refuse before any step runs, so a partial --apply never happens.
if [[ "${APPLY}" == true && "${NABLA_RUNTIME_CHANGE_APPROVED:-}" != "yes" ]]; then
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after reviewing the read-only output"
fi
require_approval() { [[ "${APPLY}" == true ]]; }

plan_only() {
  printf 'READ_ONLY: %s %s changed nothing; rerun with --apply\n' "${ACTION}" "${APP_ID}"
}

compose_project_containers() {
  docker ps -a --filter "label=com.docker.compose.project=ix-${APP_ID}" \
    --format '{{.Names}}\t{{.State}}\t{{.Status}}'
}

action_status() {
  section "Repository contract (${APP_ID})"
  field '"status=\(.status) deploy=\(.deploy // "none") env=\(.env_layout)"'
  field '"gaps: \(if (.gaps | length) == 0 then "none" else (.gaps | join(", ")) end)"'
  section "TrueNAS App"
  midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
    jq -r 'if length == 1 then "state=\(.[0].state) custom_app=\(.[0].custom_app) version=\(.[0].version)" else "App absent" end'
  section "Containers"
  compose_project_containers || true
}

action_storage() {
  if require_approval; then
    bash scripts/truenas/bootstrap-repository-storage.sh --apply "${APP_ID}"
  fi
  bash scripts/truenas/bootstrap-repository-storage.sh --check "${APP_ID}"
}

action_secrets() {
  case "$(field .env_layout)" in
    n/a) info "${APP_ID} declares no runtime env_file"; return 0 ;;
    legacy) fail "${APP_ID} still reads a legacy env_file path: migrate it to /mnt/cpool/secrets/runtime/${APP_ID}/ first" ;;
    unmanaged) fail "${APP_ID} has no entry in config/secrets/manifest.json" ;;
  esac
  # materialize_runtime.py reads Vaultwarden (BW_SESSION) and never prints values.
  if require_approval; then
    python3 scripts/secrets/materialize_runtime.py --app "${APP_ID}" --install
  fi
  python3 scripts/secrets/materialize_runtime.py --app "${APP_ID}" --verify
}

action_deploy() {
  local deploy mode="--check"
  deploy="$(field '.deploy // ""')"
  if require_approval; then mode="--apply"; fi
  case "${deploy}" in
    deploy-media-stack.sh) bash scripts/truenas/deploy-media-stack.sh "${mode}" "${APP_ID}" ;;
    deploy-*.sh) bash "scripts/truenas/${deploy}" "${mode}" ;;
    custom-apps.yml)
      # The reconciler needs a reviewed plan hash and a typed acknowledgement:
      # print the plan and let the operator run --apply with both.
      python3 scripts/truenas/reconcile-custom-apps.py --check
      [[ "${mode}" == "--check" ]] ||
        info "apply with: python3 scripts/truenas/reconcile-custom-apps.py --apply --expected-plan-hash <hash> --acknowledge <text>"
      ;;
    "native App") fail "${APP_ID} is a native catalog App: migrate it to a Custom App before deploying from Git" ;;
    *) fail "${APP_ID} has no deployment path (gap NO_DEPLOY_PATH)" ;;
  esac
}

action_restart() {
  local state
  state="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" | jq -r 'if length == 1 then .[0].state else "MISSING" end')"
  info "current state: ${state}"
  [[ "${state}" != "MISSING" ]] || fail "${APP_ID} is not installed: use deploy"
  [[ "${state}" != "DEPLOYING" ]] || fail "${APP_ID} is DEPLOYING; observe it, do not restart"
  if ! require_approval; then
    plan_only
    return 0
  fi
  # shellcheck source=../lib/truenas.sh
  source "${SCRIPT_DIR}/../lib/truenas.sh"
  truenas_job_compact app.redeploy "${APP_ID}"
  bash scripts/truenas/verify-app-runtime-health.sh "${APP_ID}"
}

action_diagnose() {
  action_status
  section "Container health"
  bash scripts/truenas/verify-app-runtime-health.sh "${APP_ID}" || warn "runtime health check failed"
  section "Specialised diagnostics"
  field 'if (.diagnose | length) == 0 then "none: use docker logs --tail 200 <container> deliberately" else .diagnose[] | "scripts/truenas/\(.)" end'
}

action_monitor() {
  section "Availability probes (x-nabla monitoring)"
  field 'if (.monitored | length) == 0 then "none (gap NO_AVAILABILITY_PROBE when active)" else .monitored[] end'
  section "Prometheus metrics"
  field 'if (.metrics | length) == 0 then "none" else .metrics[] end'
  info "live state: scripts/truenas/diagnose-prometheus-targets.sh and Gatus/Uptime Kuma"
}

action_backup() {
  local stamp dataset class database
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  section "ZFS snapshots (recursive=false, manual-<app>-<UTC>)"
  while IFS=$'\t' read -r dataset class; do
    [[ -n "${dataset}" ]] || continue
    if [[ "${class}" == "none (noSnapshot)" ]]; then
      info "skip ${dataset}: excluded from snapshots by policy"
      continue
    fi
    if require_approval; then
      zfs snapshot "${dataset}@manual-${APP_ID}-${stamp}"
      ok "snapshot ${dataset}@manual-${APP_ID}-${stamp}"
    else
      printf 'PLAN: zfs snapshot %s@manual-%s-%s (class %s)\n' "${dataset}" "${APP_ID}" "${stamp}" "${class}"
    fi
  done < <(field '.snapshot | to_entries[] | "\(.key)\t\(.value // "unclassified")"')

  section "Logical PostgreSQL backup"
  mapfile -t databases < <(field '.db_backup[]')
  if ((${#databases[@]} == 0)); then
    info "no database of ${APP_ID} is in the postgres-backup list"
    return 0
  fi
  for database in "${databases[@]}"; do
    if require_approval; then
      docker compose --project-directory apps/postgres-backup --file apps/postgres-backup/compose.yml \
        --profile manual run --rm --no-deps \
        -e "BACKUP_DATABASES=${database}" -e BACKUP_REQUIRE_ALL=true postgres-backup
    else
      printf 'PLAN: pg_dump %s through apps/postgres-backup (one-off, BACKUP_REQUIRE_ALL=true)\n' "${database}"
    fi
  done
}

case "${ACTION}" in
  status) action_status ;;
  storage) action_storage ;;
  secrets) action_secrets ;;
  deploy) action_deploy ;;
  restart) action_restart ;;
  diagnose) action_diagnose ;;
  monitor) action_monitor ;;
  backup) action_backup ;;
esac
