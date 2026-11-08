# shellcheck shell=bash
# Shared contract for single-App TrueNAS Custom App deployers
# (deploy-joplin.sh, deploy-scanopy.sh): explicit --check/--apply modes, the
# canonical checkout gate and middleware reconciliation through lib/truenas.sh.
# Sourcing this file mutates nothing; app_deploy_reconcile is the only mutator.

# Usage: app_deploy_mode "<argv1>" "<script name>" -> prints the validated mode.
app_deploy_mode() {
  local mode="${1:---check}" script="${2:-$0}"
  case "${mode}" in
  --check | --apply) printf '%s\n' "${mode}" ;;
  *)
    printf 'Usage: sudo bash %s [--check|--apply]\n' "${script}" >&2
    return 2
    ;;
  esac
}

# Root, required commands and the canonical TrueNAS checkout; leaves the shell
# in the canonical root and reports Git provenance.
app_deploy_canonical_checkout() {
  local canonical_root="${1:?canonical root is required}"
  local root
  shift
  require_root "run with sudo so TrueNAS middleware and ZFS can be managed"
  require_commands docker git grep jq midclt stat "$@"
  root="$(git rev-parse --show-toplevel)"
  [[ "${root}" == "${canonical_root}" ]] ||
    fail "run from canonical TrueNAS checkout ${canonical_root}; current checkout is ${root}"
  cd "${canonical_root}" || fail "cannot enter ${canonical_root}"
  truenas_repo_provenance "${canonical_root}"
}

app_deploy_compose_validate() {
  local compose_path="${1:?compose path is required}"
  [[ -f "${compose_path}" && ! -L "${compose_path}" ]] ||
    fail "missing or symlinked Compose declaration: ${compose_path}"
  docker compose -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution
}

# Stable machine-readable preflight report for --check runs.
app_deploy_check_report() {
  local app_id="${1:?TrueNAS app id is required}"
  truenas_app_summary "${app_id}"
  printf '%s\n' "${app_id}_preflight=verified" "${app_id}_mutations=0" \
    "${app_id}_runtime_acceptance=NOT_VERIFIED"
}

# --apply: reconcile the Custom App through the middleware, wait for RUNNING
# and prove the App is uniquely registered. Requires an explicit approval.
app_deploy_reconcile() {
  local app_id="${1:?TrueNAS app id is required}"
  local compose_path="${2:?compose path is required}"
  local wait_seconds="${3:-600}"
  [[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
    fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check preflight"
  truenas_reconcile_custom_app "${app_id}" "${compose_path}"
  truenas_app_query_by_id "${app_id}" | jq -e 'length == 1' >/dev/null ||
    fail "TrueNAS app ${app_id} is not uniquely present after reconciliation"
  truenas_wait_app_running "${app_id}" "${wait_seconds}" 5
  truenas_app_summary "${app_id}"
  printf 'Expected Custom App YAML include:\n'
  printf 'include:\n  - %s\n' "${compose_path}"
}
