#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
REPO_ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
OPERATOR_USER="${NABLA_K8S_OPERATOR_USER:-albandrieu}"
CALL_TIMEOUT="${NABLA_MIDCLT_TIMEOUT_SECONDS:-180}"
APP_JOB_TIMEOUT="${NABLA_APP_JOB_TIMEOUT_SECONDS:-900}"
APP_WAIT="${NABLA_APP_START_WAIT_SECONDS:-600}"
EXTRA_RESUME_APPS="${NABLA_REBOOT_RESUME_STOPPED_APPS:-}"
TALOS_WAIT="${NABLA_TALOS_SHUTDOWN_TIMEOUT:-15m}"
TALOS_ENDPOINT="${NABLA_TALOS_ENDPOINT:-172.17.0.50}"
TALOS_NODES=(172.17.0.51 172.17.0.52 172.17.0.50)
VM_NAMES=(taloscp01 taloswk01 taloswk02)

BUNDLE_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
PLANNER="${NABLA_REBOOT_PLANNER:-${SCRIPT_DIR}/plan-app-lifecycle-order.py}"
IPAM_CHECK="${NABLA_IPAM_CHECK_SCRIPT:-${SCRIPT_DIR}/migrate-docker-address-pool.sh}"
RESUME_RECONCILER="${NABLA_REBOOT_RESUME_RECONCILER:-${SCRIPT_DIR}/reconcile-reboot-resume.sh}"
ORPHAN_SHIMS="${NABLA_ORPHAN_SHIM_DIAGNOSTIC:-${SCRIPT_DIR}/diagnose-docker-orphan-shims.sh}"
[[ -f "${PLANNER}" ]] || PLANNER="${REPO_ROOT}/scripts/truenas/plan-app-lifecycle-order.py"
[[ -f "${IPAM_CHECK}" ]] || IPAM_CHECK="${REPO_ROOT}/scripts/truenas/migrate-docker-address-pool.sh"
[[ -f "${RESUME_RECONCILER}" ]] || RESUME_RECONCILER="${REPO_ROOT}/scripts/truenas/reconcile-reboot-resume.sh"
[[ -f "${ORPHAN_SHIMS}" ]] || ORPHAN_SHIMS="${REPO_ROOT}/scripts/truenas/diagnose-docker-orphan-shims.sh"

usage() {
  echo "usage: sudo bash scripts/truenas/reboot-homelab.sh [--check|--prepare|--continue-prepare|--post-reboot-check|--resume|--verify]"
}

case "${MODE}" in
  --check | --prepare | --continue-prepare | --post-reboot-check | --resume | --verify) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

require_root "run as root on TrueNAS"
require_commands midclt jq docker python3 timeout getent awk tr sha256sum cmp
[[ -f "${PLANNER}" ]] || fail "lifecycle planner not found: ${PLANNER}"
[[ -f "${REPO_ROOT}/catalog/services.json" ]] || fail "services catalog not found under ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/catalog/service-topology.json" ]] || fail "topology catalog not found under ${REPO_ROOT}"

operator_home="$(getent passwd "${OPERATOR_USER}" | cut -d: -f6)"
[[ -n "${operator_home}" && -d "${operator_home}" ]] ||
  fail "cannot resolve persistent HOME for ${OPERATOR_USER}"
TALOSCONFIG="${NABLA_TALOSCONFIG:-${operator_home}/.config/nabla/talos/talosconfig}"
KUBECONFIG="${NABLA_KUBECONFIG:-${operator_home}/.config/nabla/talos/kubeconfig}"
TALOSCTL="${NABLA_TALOSCTL:-/mnt/cpool/tools/bin/talosctl}"
KUBECTL="${NABLA_KUBECTL:-/mnt/cpool/tools/bin/kubectl}"
[[ -x "${TALOSCTL}" ]] || fail "talosctl not executable: ${TALOSCTL}"
[[ -x "${KUBECTL}" ]] || fail "kubectl not executable: ${KUBECTL}"
[[ -r "${TALOSCONFIG}" ]] || fail "talosconfig not readable: ${TALOSCONFIG}"
[[ -r "${KUBECONFIG}" ]] || fail "kubeconfig not readable: ${KUBECONFIG}"

run_operator() {
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "${OPERATOR_USER}" -- env \
      HOME="${operator_home}" \
      PATH="/mnt/cpool/tools/bin:/usr/bin:/bin" \
      TALOSCONFIG="${TALOSCONFIG}" \
      KUBECONFIG="${KUBECONFIG}" \
      "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -u "${OPERATOR_USER}" env \
      HOME="${operator_home}" \
      PATH="/mnt/cpool/tools/bin:/usr/bin:/bin" \
      TALOSCONFIG="${TALOSCONFIG}" \
      KUBECONFIG="${KUBECONFIG}" \
      "$@"
  else
    fail "neither runuser nor sudo is available to execute cluster clients as ${OPERATOR_USER}"
  fi
}

midclt_bounded() {
  timeout "${CALL_TIMEOUT}" midclt call "$@"
}

truenas_ready() {
  local raw
  raw="$(midclt_bounded system.ready | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  [[ "${raw}" == "true" ]]
}

app_json() {
  midclt_bounded app.query "[[\"id\",\"=\",\"$1\"]]"
}

app_state() {
  app_json "$1" | jq -r 'if length == 1 then .[0].state else "UNKNOWN" end'
}

bundle_identity() {
  local source="workspace"
  [[ -f "${BUNDLE_ROOT}/SOURCE_COMMIT" ]] && source="$(cat "${BUNDLE_ROOT}/SOURCE_COMMIT")"
  printf '%s %s\n' "${source}" "$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
}

verify_bundle_integrity() {
  [[ -f "${BUNDLE_ROOT}/SHA256SUMS" ]] || return 0
  (cd "${BUNDLE_ROOT}" && sha256sum --quiet -c SHA256SUMS) ||
    fail "bundle checksum verification failed under ${BUNDLE_ROOT}"
}

# Prepare-side bounded evidence only. app.start diagnostics are owned by the
# resume reconciler. Running/Restarting but pid=0 is a probable orphaned containerd shim
# and must only use the exact-container recovery helper.
diagnose_app_runtime() {
  local app="$1" project="ix-$1" id
  local -a ids=()
  printf 'DIAG app=%s state=%s\n' "${app}" "$(app_state "${app}")" >&2
  mapfile -t ids < <(docker ps -aq --filter "label=com.docker.compose.project=${project}")
  for id in "${ids[@]}"; do
    docker inspect "${id}" |
      jq -r '.[0] | "  container=\(.Name|ltrimstr("/")) status=\(.State.Status) running=\(.State.Running) restarting=\(.State.Restarting) pid=\(.State.Pid) restarts=\(.RestartCount) exit=\(.State.ExitCode)"' >&2 || true
  done
  [[ -f "${ORPHAN_SHIMS}" ]] && bash "${ORPHAN_SHIMS}" --check || true
}

vm_policy_gate() {
  local payload name row shutdown_timeout
  payload="$(midclt_bounded vm.query)"
  for name in "${VM_NAMES[@]}"; do
    row="$(
      jq -ce --arg name "${name}" \
        '[.[]|select(.name==$name)]|if length==1 then .[0] else error("VM count mismatch") end' \
        <<<"${payload}"
    )" || fail "unable to resolve ${name}"
    [[ "$(jq -r '.autostart' <<<"${row}")" == true ]] || fail "${name}: autostart=false"
    shutdown_timeout="$(jq -r '.shutdown_timeout // 0' <<<"${row}")"
    ((shutdown_timeout >= 120)) ||
      fail "${name}: shutdown_timeout=${shutdown_timeout}s; require >=120s"
  done
  ok "Talos VMs autostart=true and have graceful shutdown timeout >=120s"
}

talos_api_check() {
  local node="$1" seconds="${2:-30}" phase="${3:-preflight}" output
  output="$(
    run_operator timeout "${seconds}" "${TALOSCTL}" \
      --endpoints "${TALOS_ENDPOINT}" \
      --nodes "${node}" \
      version 2>&1
  )" || {
    printf 'Talos API %s failed target=%s endpoint=%s\n%s\n' \
      "${phase}" "${node}" "${TALOS_ENDPOINT}" "${output}" >&2
    return 1
  }
}

cluster_client_preflight() {
  local node
  run_operator "${KUBECTL}" get nodes -o wide
  for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
    talos_api_check "${node}" 30 preflight ||
      fail "Talos API preflight failed for ${node} via endpoint ${TALOS_ENDPOINT}"
  done
}

make_plans() {
  local apps="$1" dir="$2"
  python3 "${PLANNER}" \
    --apps "${apps}" \
    --states RUNNING,DEPLOYING,CRASHED,ERROR,STOPPING \
    --services "${REPO_ROOT}/catalog/services.json" \
    --topology "${REPO_ROOT}/catalog/service-topology.json" \
    --pretty >"${dir}/shutdown-plan.json"
  python3 "${PLANNER}" \
    --apps "${apps}" \
    --states RUNNING,DEPLOYING \
    --include-apps "${EXTRA_RESUME_APPS}" \
    --services "${REPO_ROOT}/catalog/services.json" \
    --topology "${REPO_ROOT}/catalog/service-topology.json" \
    --pretty >"${dir}/resume-plan.json"
}

print_plan_summary() {
  local dir="$1" explicit_resume="${EXTRA_RESUME_APPS:-}" plan unmapped
  local -a saved_explicit_resume=()
  if [[ -f "${dir}/explicit-resume.txt" ]]; then
    mapfile -t saved_explicit_resume <"${dir}/explicit-resume.txt"
    explicit_resume="${saved_explicit_resume[*]}"
  fi

  printf '\nApps that will resume after reboot:\n'
  jq -r \
    '.start_waves as $w|(.start_wave_phases//[]) as $p|range(0;$w|length) as $i|"  wave \($i+1) [\($p[$i]//"topology")]: \($w[$i]|join(" "))"' \
    "${dir}/resume-plan.json"
  printf '\nShutdown waves (exact reverse dependency/phase order):\n'
  jq -r '.stop_waves|to_entries[]|"  wave \(.key+1): \(.value|join(" "))"' \
    "${dir}/shutdown-plan.json"
  printf '\nExplicit maintenance-stopped Apps scheduled for resume: %s\n' \
    "${explicit_resume:-none}"

  for plan in shutdown-plan resume-plan; do
    unmapped="$(jq -r '.unmapped_apps|join(" ")' "${dir}/${plan}.json")"
    [[ -z "${unmapped}" ]] || warn "${plan}: no topology mapping for: ${unmapped}"
  done
}

latest_state_dir() {
  [[ -f "${STATE_ROOT}/latest" ]] || fail "no reboot state manifest at ${STATE_ROOT}/latest"
  local dir
  dir="$(cat "${STATE_ROOT}/latest")"
  [[ -d "${dir}" ]] || fail "recorded reboot state directory is missing: ${dir}"
  printf '%s\n' "${dir}"
}

validate_prepare_manifest() {
  local dir="$1" f
  for f in \
    apps-before.json \
    vms-before.json \
    docker-config-before.json \
    kubernetes-nodes-before.json \
    boot-id-before \
    shutdown-plan.json \
    resume-plan.json \
    resume-apps.txt \
    intentional-stopped.txt \
    preexisting-failed.txt; do
    [[ -f "${dir}/${f}" ]] || fail "incomplete reboot manifest: missing ${dir}/${f}"
  done
}

record_prepare_history() {
  printf '%s action=%s bundle=%s identity=%s\n' \
    "$(date -Iseconds)" "$2" "${BUNDLE_ROOT}" "$(bundle_identity)" \
    >>"$1/prepare-history.log"
}

guard_no_incomplete_prepare() {
  [[ -d "${STATE_ROOT}" ]] || return 0
  local current dir before phase
  current="$(midclt_bounded system.boot_id | tr -d '"')"
  for dir in "${STATE_ROOT}"/*-"${current}"; do
    [[ -d "${dir}" && -f "${dir}/boot-id-before" ]] || continue
    before="$(cat "${dir}/boot-id-before")"
    [[ "${before}" == "${current}" ]] || continue
    phase="$(cat "${dir}/phase" 2>/dev/null || true)"
    if [[ "${phase}" == PREPARING || "${phase}" == PREPARED ]] ||
      {
        [[ -z "${phase}" ]] &&
          [[ -f "${dir}/shutdown-plan.json" ]] &&
          [[ -f "${dir}/resume-plan.json" ]]
      }; then
      fail "same-boot transaction exists at ${dir} phase=${phase:-legacy}; use --continue-prepare; never rerun --prepare"
    fi
  done
}

wait_app_stopped() {
  local app="$1" deadline=$((SECONDS + APP_WAIT))
  while ((SECONDS < deadline)); do
    [[ "$(app_state "${app}")" == STOPPED ]] && return 0
    sleep 5
  done
  diagnose_app_runtime "${app}"
  return 1
}

continue_prepare() {
  local dir="$1" app state node deadline running
  local -a apps=() leftovers=()
  validate_prepare_manifest "${dir}"
  printf 'PREPARING\n' >"${dir}/phase"
  record_prepare_history "${dir}" continue-prepare

  printf '\nStopping TrueNAS Apps in reverse dependency/phase order...\n'
  mapfile -t apps < <(jq -r '.stop_order[]' "${dir}/shutdown-plan.json")
  for app in "${apps[@]}"; do
    state="$(app_state "${app}")"
    if [[ "${state}" == STOPPED ]]; then
      printf 'SKIP %s already STOPPED\n' "${app}"
      continue
    fi
    printf 'STOP %s state=%s\n' "${app}" "${state}"
    if ! timeout "${APP_JOB_TIMEOUT}" midclt call -j app.stop "${app}" >/dev/null; then
      diagnose_app_runtime "${app}"
      fail "${app}: app.stop failed/timed out; preserve manifest and use --continue-prepare"
    fi
    wait_app_stopped "${app}" ||
      fail "${app}: did not reach STOPPED; preserve manifest and use --continue-prepare"
  done

  mapfile -t leftovers < <(docker ps --format '{{.Names}}')
  if ((${#leftovers[@]})); then
    printf 'Running Docker leftovers:\n  %s\n' "${leftovers[*]}" >&2
    [[ -f "${ORPHAN_SHIMS}" ]] && bash "${ORPHAN_SHIMS}" --check || true
    fail "refusing Talos/host shutdown while Docker containers still run"
  fi
  ok "no running Docker container remains"

  printf '\nGracefully shutting down Talos workers, then control plane...\n'
  for node in "${TALOS_NODES[@]}"; do
    run_operator timeout 20m "${TALOSCTL}" \
      --endpoints "${TALOS_ENDPOINT}" \
      --nodes "${node}" \
      shutdown --wait --timeout "${TALOS_WAIT}" ||
      fail "${node}: graceful Talos shutdown failed; never use shutdown --force"
  done

  deadline=$((SECONDS + 300))
  running=3
  while ((SECONDS < deadline)); do
    running="$(
      midclt_bounded vm.query |
        jq '[.[]|select((.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02") and (.status.state//"UNKNOWN")!="STOPPED")]|length'
    )"
    ((running == 0)) && break
    sleep 5
  done
  ((running == 0)) || fail "Talos VMs did not all reach STOPPED"

  printf 'PREPARED\n' >"${dir}/phase"
  record_prepare_history "${dir}" prepared
  printf 'SUCCESS: homelab prepared for supported TrueNAS reboot. manifest=%s\n' "${dir}"
}

# Re-derive ordering from the original snapshot with the current planner while
# freezing membership. This repairs planner bugs without ever replacing the
# forensic resume-plan.json from the transaction.
build_effective_resume_plan() {
  local dir="$1" effective="${1}/resume-plan-effective.json" explicit=""
  local old_members new_members

  if [[ -f "${dir}/explicit-resume.txt" ]]; then
    explicit="$(tr '\n' ' ' <"${dir}/explicit-resume.txt")"
  fi

  python3 "${PLANNER}" \
    --apps "${dir}/apps-before.json" \
    --states RUNNING,DEPLOYING \
    --include-apps "${explicit}" \
    --services "${REPO_ROOT}/catalog/services.json" \
    --topology "${REPO_ROOT}/catalog/service-topology.json" \
    --pretty >"${effective}"

  old_members="$(jq -cS '.selected_apps' "${dir}/resume-plan.json")"
  new_members="$(jq -cS '.selected_apps' "${effective}")"
  if [[ "${old_members}" != "${new_members}" ]]; then
    rm -f "${effective}"
    fail "refusing ordering repair because selected App membership changed"
  fi

  if ! cmp -s \
    <(jq -c '.start_order' "${dir}/resume-plan.json") \
    <(jq -c '.start_order' "${effective}"); then
    warn "resume order repaired; original resume-plan.json preserved and membership is identical"
    printf '%s derived-order=%s\n' \
      "$(date -Iseconds)" "$(jq -c '.start_waves' "${effective}")" \
      >>"${dir}/resume-order-history.log"
  fi
  printf '%s\n' "${effective}"
}

run_resume_reconciler() {
  local dir="$1" effective tmp_root tmp_state rc
  [[ -f "${RESUME_RECONCILER}" ]] ||
    fail "resume reconciler not found: ${RESUME_RECONCILER}"
  effective="$(build_effective_resume_plan "${dir}")"
  tmp_root="$(mktemp -d)"
  tmp_state="${tmp_root}/state"
  mkdir -p "${tmp_state}"
  cp "${effective}" "${tmp_state}/resume-plan.json"
  cp "${dir}/boot-id-before" "${tmp_state}/boot-id-before"
  printf '%s\n' "${tmp_state}" >"${tmp_root}/latest"

  if NABLA_REBOOT_STATE_ROOT="${tmp_root}" \
    NABLA_MIDCLT_TIMEOUT_SECONDS="${CALL_TIMEOUT}" \
    NABLA_APP_JOB_TIMEOUT_SECONDS="${APP_JOB_TIMEOUT}" \
    NABLA_APP_START_WAIT_SECONDS="${APP_WAIT}" \
    bash "${RESUME_RECONCILER}" --apply; then
    printf 'RESUMED\n' >"${dir}/phase"
    rm -rf "${tmp_root}"
    return 0
  else
    rc=$?
  fi

  rm -rf "${tmp_root}"
  fail "resume reconciler failed; original manifest preserved (rc=${rc})"
}

verify_bundle_integrity

if [[ "${MODE}" == --check ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' EXIT
  midclt_bounded app.query >"${tmp}/apps-before.json"
  make_plans "${tmp}/apps-before.json" "${tmp}"
  vm_policy_gate
  cluster_client_preflight
  print_plan_summary "${tmp}"
  printf 'READ-ONLY: reboot preflight passed; no App or VM changed.\n'
  exit 0
fi

if [[ "${MODE}" == --prepare ]]; then
  truenas_ready || fail "TrueNAS system.ready is not true"
  vm_policy_gate
  cluster_client_preflight
  guard_no_incomplete_prepare

  mkdir -p "${STATE_ROOT}"
  chmod 700 "${STATE_ROOT}"
  boot_id="$(midclt_bounded system.boot_id | tr -d '"')"
  state_dir="${STATE_ROOT}/$(date +%Y%m%d-%H%M%S)-${boot_id}"
  mkdir -p "${state_dir}"
  chmod 700 "${state_dir}"

  midclt_bounded app.query >"${state_dir}/apps-before.json"
  midclt_bounded vm.query >"${state_dir}/vms-before.json"
  midclt_bounded docker.config >"${state_dir}/docker-config-before.json"
  docker network ls >"${state_dir}/docker-networks-before.txt"
  run_operator "${KUBECTL}" get nodes -o json >"${state_dir}/kubernetes-nodes-before.json"
  printf '%s\n' "${boot_id}" >"${state_dir}/boot-id-before"
  make_plans "${state_dir}/apps-before.json" "${state_dir}"
  printf '%s\n' "${EXTRA_RESUME_APPS}" |
    awk 'BEGIN{RS="[,[:space:]]+"} NF{print}' |
    sort -u >"${state_dir}/explicit-resume.txt"
  jq -r '.[]|select(.state=="STOPPED")|.id' "${state_dir}/apps-before.json" |
    sort -u |
    grep -Fvx -f "${state_dir}/explicit-resume.txt" >"${state_dir}/intentional-stopped.txt" || true
  jq -r '.[]|select(.state=="CRASHED" or .state=="ERROR")|.id' \
    "${state_dir}/apps-before.json" |
    sort -u >"${state_dir}/preexisting-failed.txt"
  jq -r '.selected_apps[]' "${state_dir}/resume-plan.json" >"${state_dir}/resume-apps.txt"
  bundle_identity >"${state_dir}/orchestrator-identity.txt"
  printf 'PREPARING\n' >"${state_dir}/phase"
  record_prepare_history "${state_dir}" prepare
  printf '%s\n' "${state_dir}" >"${STATE_ROOT}/latest"
  print_plan_summary "${state_dir}"
  continue_prepare "${state_dir}"
  exit 0
fi

if [[ "${MODE}" == --continue-prepare ]]; then
  truenas_ready || fail "TrueNAS system.ready is not true"
  state_dir="$(latest_state_dir)"
  validate_prepare_manifest "${state_dir}"
  before_boot_id="$(cat "${state_dir}/boot-id-before")"
  current_boot_id="$(midclt_bounded system.boot_id | tr -d '"')"
  [[ "${current_boot_id}" == "${before_boot_id}" ]] ||
    fail "boot_id changed; refusing pre-reboot continuation after reboot"
  phase="$(cat "${state_dir}/phase" 2>/dev/null || true)"
  [[ "${phase}" == PREPARING || -z "${phase}" ]] ||
    fail "manifest phase=${phase} cannot be continued safely"
  printf 'Continuing preserved reboot manifest: %s\n' "${state_dir}"
  print_plan_summary "${state_dir}"
  continue_prepare "${state_dir}"
  exit 0
fi

state_dir="$(latest_state_dir)"
validate_prepare_manifest "${state_dir}"
before_boot_id="$(cat "${state_dir}/boot-id-before")"
current_boot_id="$(midclt_bounded system.boot_id | tr -d '"')"

if [[ "${MODE}" == --post-reboot-check ]]; then
  [[ "${current_boot_id}" != "${before_boot_id}" ]] || fail "boot_id did not change"
  truenas_ready || fail "TrueNAS has not completed boot"
  [[ -f "${IPAM_CHECK}" ]] || fail "IPAM post-reboot helper not found: ${IPAM_CHECK}"
  bash "${IPAM_CHECK}" --post-reboot-check

  vm_payload="$(midclt_bounded vm.query)"
  for name in "${VM_NAMES[@]}"; do
    jq -e --arg name "${name}" \
      '[.[]|select(.name==$name and .autostart==true and (.status.state//"UNKNOWN")=="RUNNING")]|length==1' \
      <<<"${vm_payload}" >/dev/null ||
      fail "${name}: expected autostart=true and RUNNING"
  done
  for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
    talos_api_check "${node}" 60 post-reboot || fail "Talos API not ready: ${node}"
  done
  run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=5m
  run_operator "${KUBECTL}" get nodes -o wide
  printf 'SUCCESS: post-reboot acceptance passed.\n'
  exit 0
fi

if [[ "${MODE}" == --resume ]]; then
  [[ "${current_boot_id}" != "${before_boot_id}" ]] ||
    fail "refusing resume before an actual reboot"
  truenas_ready || fail "TrueNAS is not ready"
  run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=5m
  mapfile -t nodes < <(run_operator "${KUBECTL}" get nodes -o name)
  for node in "${nodes[@]}"; do
    run_operator "${KUBECTL}" uncordon "${node}" >/dev/null 2>&1 || true
  done
  run_operator "${KUBECTL}" get nodes

  # app.start and DEPLOYING handling live in the idempotent reconciler.
  run_resume_reconciler "${state_dir}"
  exit 0
fi

# --verify
[[ "${current_boot_id}" != "${before_boot_id}" ]] || fail "reboot not observed"
truenas_ready || fail "TrueNAS is not ready"
[[ -f "${RESUME_RECONCILER}" ]] || fail "resume reconciler not found: ${RESUME_RECONCILER}"
NABLA_REBOOT_STATE_ROOT="${STATE_ROOT}" bash "${RESUME_RECONCILER}" --check ||
  fail "saved Apps failed final RUNNING acceptance"
while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  state="$(app_state "${app}")"
  [[ "${state}" == STOPPED ]] ||
    warn "intentional pre-reboot STOPPED app ${app} is now ${state}"
done <"${state_dir}/intentional-stopped.txt"
vm_policy_gate
run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=60s
printf 'SUCCESS: homelab reboot lifecycle acceptance passed.\n'
