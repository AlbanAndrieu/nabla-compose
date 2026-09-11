#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
REPO_ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
OPERATOR_USER="${NABLA_K8S_OPERATOR_USER:-albandrieu}"
CALL_TIMEOUT="${NABLA_MIDCLT_TIMEOUT_SECONDS:-180}"
APP_WAIT="${NABLA_APP_START_WAIT_SECONDS:-600}"
TALOS_WAIT="${NABLA_TALOS_SHUTDOWN_TIMEOUT:-15m}"
EXTRA_RESUME_APPS="${NABLA_REBOOT_RESUME_STOPPED_APPS:-}"
TALOS_ENDPOINT="${NABLA_TALOS_ENDPOINT:-172.17.0.50}"
TALOS_NODES=(172.17.0.51 172.17.0.52 172.17.0.50)
VM_NAMES=(taloscp01 taloswk01 taloswk02)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
PLANNER="${NABLA_REBOOT_PLANNER:-${SCRIPT_DIR}/plan-app-lifecycle-order.py}"
[[ -f "${PLANNER}" ]] || PLANNER="${REPO_ROOT}/scripts/truenas/plan-app-lifecycle-order.py"
IPAM_CHECK="${NABLA_IPAM_CHECK_SCRIPT:-${SCRIPT_DIR}/migrate-docker-address-pool.sh}"
[[ -f "${IPAM_CHECK}" ]] || IPAM_CHECK="${REPO_ROOT}/scripts/truenas/migrate-docker-address-pool.sh"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

usage() {
  printf '%s\n' \
    "usage: sudo bash scripts/truenas/reboot-homelab.sh [--check|--prepare|--continue-prepare|--post-reboot-check|--resume|--verify]"
}

case "${MODE}" in
  --check | --prepare | --continue-prepare | --post-reboot-check | --resume | --verify) ;;
  *)
    usage
    exit 1
    ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq docker python3 timeout getent pgrep awk tr ps sha256sum; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
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

bundle_identity() {
  local source="workspace" script_sha
  [[ -f "${BUNDLE_ROOT}/SOURCE_COMMIT" ]] && source="$(cat "${BUNDLE_ROOT}/SOURCE_COMMIT")"
  script_sha="$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')"
  printf '%s %s\n' "${source}" "${script_sha}"
}

verify_bundle_integrity() {
  [[ -f "${BUNDLE_ROOT}/SHA256SUMS" ]] || return 0
  if ! (cd "${BUNDLE_ROOT}" && sha256sum --quiet -c SHA256SUMS); then
    fail "bundle checksum verification failed under ${BUNDLE_ROOT}; refuse lifecycle mutation"
  fi
}

app_state() {
  local app="$1"
  midclt_bounded app.query |
    jq -r --arg app "${app}" '
      [.[] | select(.id == $app or .name == $app)] |
      if length == 1 then .[0].state else "UNKNOWN" end
    '
}

diagnose_app_runtime() {
  local app="$1"
  local project="ix-${app}"
  local id row full_id name status running restarting pid
  local -a ids=()

  mapfile -t ids < <(
    docker ps -aq --filter "label=com.docker.compose.project=${project}"
  )

  if ((${#ids[@]} == 0)); then
    warn "${app}: no Docker containers found with Compose project ${project}"
    return 0
  fi

  printf 'Runtime evidence for failed App %s:\n' "${app}" >&2
  for id in "${ids[@]}"; do
    row="$(
      docker inspect "${id}" |
        jq -r '.[0] | [
          .Id,
          (.Name | ltrimstr("/")),
          (.State.Status // "unknown"),
          ((.State.Running // false) | tostring),
          ((.State.Restarting // false) | tostring),
          ((.State.Pid // 0) | tostring)
        ] | @tsv'
    )"
    IFS=$'\t' read -r full_id name status running restarting pid <<<"${row}"
    printf '  container=%s id=%s status=%s running=%s restarting=%s pid=%s\n' \
      "${name}" "${full_id}" "${status}" "${running}" "${restarting}" "${pid}" >&2

    if [[ "${pid}" == "0" && ( "${running}" == "true" || "${restarting}" == "true" ) ]]; then
      warn "${app}/${name}: probable orphaned containerd shim: Docker reports Running/Restarting but pid=0"
      pgrep -af containerd-shim-runc-v2 |
        awk -v cid="${full_id}" 'index($0, "-id " cid) {print "  shim=" $0}' >&2 || true
      warn "run diagnose-docker-orphan-shims.sh --check and use its exact-id --recover flow only after review"
    fi
  done
}

diagnose_running_containers() {
  local name row full_id status running restarting pid restart_policy
  local -a names=("$@")

  for name in "${names[@]}"; do
    row="$(
      docker inspect "${name}" |
        jq -r '.[0] | [
          .Id,
          (.State.Status // "unknown"),
          ((.State.Running // false) | tostring),
          ((.State.Restarting // false) | tostring),
          ((.State.Pid // 0) | tostring),
          (.HostConfig.RestartPolicy.Name // "")
        ] | @tsv'
    )"
    IFS=$'\t' read -r full_id status running restarting pid restart_policy <<<"${row}"
    printf '  container=%s id=%s status=%s running=%s restarting=%s pid=%s restart=%s\n' \
      "${name}" "${full_id}" "${status}" "${running}" "${restarting}" "${pid}" "${restart_policy}" >&2
    if [[ "${pid}" == "0" && ( "${running}" == "true" || "${restarting}" == "true" ) ]]; then
      warn "${name}: Docker reports Running/Restarting with pid=0; inspect for an orphaned containerd shim before retrying"
    fi
  done
}

vm_policy_gate() {
  local payload name row timeout_value
  payload="$(midclt_bounded vm.query)"
  for name in "${VM_NAMES[@]}"; do
    row="$(
      jq -ce --arg name "${name}" '
        [.[] | select(.name == $name)] |
        if length == 1 then .[0] else error("VM count mismatch: " + $name) end
      ' <<<"${payload}"
    )" || fail "unable to resolve Talos VM ${name}"
    [[ "$(jq -r '.autostart' <<<"${row}")" == "true" ]] ||
      fail "${name}: autostart=false; run reconcile-talos-vm-policy.sh --apply first"
    timeout_value="$(jq -r '.shutdown_timeout // 0' <<<"${row}")"
    ((timeout_value >= 120)) ||
      fail "${name}: shutdown_timeout=${timeout_value}s; require >=120s for planned Talos shutdown"
  done
  printf 'OK: Talos VMs autostart=true and have graceful shutdown timeout >=120s\n'
}

talos_api_check() {
  local node="$1" timeout_seconds="${2:-30}" phase="${3:-preflight}" output
  if ! output="$(
    run_operator timeout "${timeout_seconds}" "${TALOSCTL}" \
      --endpoints "${TALOS_ENDPOINT}" \
      --nodes "${node}" \
      version 2>&1
  )"; then
    printf 'Talos API %s failed target=%s endpoint=%s\n%s\n' \
      "${phase}" "${node}" "${TALOS_ENDPOINT}" "${output}" >&2
    return 1
  fi
}

cluster_client_preflight() {
  run_operator "${KUBECTL}" get nodes -o wide
  for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
    talos_api_check "${node}" 30 preflight ||
      fail "Talos API preflight failed for ${node} via endpoint ${TALOS_ENDPOINT}"
  done
  printf 'OK: Kubernetes and all three Talos APIs are reachable through endpoint %s\n' \
    "${TALOS_ENDPOINT}"
}

make_plans() {
  local apps_file="$1" out_dir="$2"
  python3 "${PLANNER}" \
    --apps "${apps_file}" \
    --states RUNNING,DEPLOYING,CRASHED,ERROR,STOPPING \
    --services "${REPO_ROOT}/catalog/services.json" \
    --topology "${REPO_ROOT}/catalog/service-topology.json" \
    --pretty >"${out_dir}/shutdown-plan.json"
  python3 "${PLANNER}" \
    --apps "${apps_file}" \
    --states RUNNING,DEPLOYING \
    --include-apps "${EXTRA_RESUME_APPS}" \
    --services "${REPO_ROOT}/catalog/services.json" \
    --topology "${REPO_ROOT}/catalog/service-topology.json" \
    --pretty >"${out_dir}/resume-plan.json"
}

print_plan_summary() {
  local dir="$1" plan unmapped explicit_resume="${EXTRA_RESUME_APPS:-}"
  local -a saved_explicit_resume=()

  if [[ -f "${dir}/explicit-resume.txt" ]]; then
    mapfile -t saved_explicit_resume <"${dir}/explicit-resume.txt"
    explicit_resume="${saved_explicit_resume[*]}"
  fi

  printf '\nApps that will resume after reboot:\n'
  jq -r '.start_waves | to_entries[] | "  wave \(.key+1): \(.value|join(" "))"' \
    "${dir}/resume-plan.json"
  printf '\nShutdown waves (reverse dependency order):\n'
  jq -r '.stop_waves | to_entries[] | "  wave \(.key+1): \(.value|join(" "))"' \
    "${dir}/shutdown-plan.json"
  printf '\nExplicit maintenance-stopped Apps scheduled for resume: %s\n' "${explicit_resume:-none}"
  printf 'Other STOPPED Apps preserved: '
  jq '[.[] | select(.state=="STOPPED")] | length' "${dir}/apps-before.json"
  printf 'Pre-existing CRASHED Apps not auto-resumed: '
  jq '[.[] | select(.state=="CRASHED")] | length' "${dir}/apps-before.json"
  for plan in shutdown-plan resume-plan; do
    unmapped="$(jq -r '.unmapped_apps | join(" ")' "${dir}/${plan}.json")"
    [[ -z "${unmapped}" ]] || warn "${plan}: no topology mapping for: ${unmapped}"
  done
}

wait_app_stopped() {
  local app="$1" deadline=$((SECONDS + APP_WAIT)) state
  while ((SECONDS < deadline)); do
    state="$(app_state "${app}")"
    [[ "${state}" == "STOPPED" ]] && return 0
    sleep 5
  done
  fail "${app}: did not reach STOPPED"
}

wait_app_running() {
  local app="$1" deadline=$((SECONDS + APP_WAIT)) state
  while ((SECONDS < deadline)); do
    state="$(app_state "${app}")"
    [[ "${state}" == "RUNNING" ]] && return 0
    [[ "${state}" == "CRASHED" || "${state}" == "ERROR" ]] &&
      fail "${app}: start converged to ${state}"
    sleep 5
  done
  fail "${app}: did not reach RUNNING"
}

latest_state_dir() {
  [[ -f "${STATE_ROOT}/latest" ]] || fail "no reboot state manifest at ${STATE_ROOT}/latest"
  local dir
  dir="$(cat "${STATE_ROOT}/latest")"
  [[ -d "${dir}" ]] || fail "recorded reboot state directory is missing: ${dir}"
  printf '%s\n' "${dir}"
}

validate_prepare_manifest() {
  local dir="$1" required
  for required in \
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
    [[ -f "${dir}/${required}" ]] || fail "incomplete reboot manifest: missing ${dir}/${required}"
  done
}

guard_no_incomplete_prepare() {
  [[ -d "${STATE_ROOT}" ]] || return 0

  local dir before current phase
  current="$(midclt_bounded system.boot_id | tr -d '"')"

  for dir in "${STATE_ROOT}"/*-"${current}"; do
    [[ -d "${dir}" && -f "${dir}/boot-id-before" ]] || continue
    before="$(cat "${dir}/boot-id-before")"
    [[ "${before}" == "${current}" ]] || continue
    phase="$(cat "${dir}/phase" 2>/dev/null || true)"
    if [[ "${phase}" == "PREPARING" || "${phase}" == "PREPARED" ]] ||
      { [[ -z "${phase}" ]] && [[ -f "${dir}/shutdown-plan.json" && -f "${dir}/resume-plan.json" ]]; }; then
      fail "same-boot reboot transaction already exists at ${dir} phase=${phase:-legacy}; use --continue-prepare or complete/recover that transaction, never create a fresh --prepare"
    fi
  done
}

record_prepare_history() {
  local state_dir="$1" action="$2" identity
  identity="$(bundle_identity)"
  printf '%s action=%s bundle=%s identity=%s\n' \
    "$(date -Iseconds)" "${action}" "${BUNDLE_ROOT}" "${identity}" >>"${state_dir}/prepare-history.log"
}

continue_prepare() {
  local state_dir="$1" app state node deadline running
  local -a stop_apps=()
  local -a leftovers=()

  validate_prepare_manifest "${state_dir}"
  printf 'PREPARING\n' >"${state_dir}/phase"
  record_prepare_history "${state_dir}" "continue-prepare"

  printf '\nStopping remaining TrueNAS Apps from the preserved shutdown plan...\n'
  mapfile -t stop_apps < <(jq -r '.stop_order[]' "${state_dir}/shutdown-plan.json")
  for app in "${stop_apps[@]}"; do
    state="$(app_state "${app}")"
    if [[ "${state}" == "STOPPED" ]]; then
      printf 'SKIP %s already STOPPED\n' "${app}"
      continue
    fi
    printf 'STOP %s state=%s\n' "${app}" "${state}"
    if ! midclt_bounded -j app.stop "${app}" >/dev/null; then
      diagnose_app_runtime "${app}"
      fail "${app}: app.stop failed/timed out; preserve this manifest, remediate the blocker, then use --continue-prepare"
    fi
    wait_app_stopped "${app}"
  done

  mapfile -t leftovers < <(docker ps --format '{{.Names}}')
  if ((${#leftovers[@]})); then
    printf 'Unmanaged/running Docker containers remain after all TrueNAS Apps stopped:\n' >&2
    diagnose_running_containers "${leftovers[@]}"
    fail "refusing Talos/host shutdown while Docker containers still run; preserve this manifest and use --continue-prepare after remediation"
  fi
  printf 'OK: no running Docker container remains\n'

  printf '\nGracefully shutting down Talos workers, then control plane...\n'
  for node in "${TALOS_NODES[@]}"; do
    printf 'TALOS SHUTDOWN %s via endpoint %s (graceful cordon/drain; never --force)\n' \
      "${node}" "${TALOS_ENDPOINT}"
    run_operator timeout 20m "${TALOSCTL}" \
      --endpoints "${TALOS_ENDPOINT}" \
      --nodes "${node}" \
      shutdown --wait --timeout "${TALOS_WAIT}" ||
      fail "${node}: graceful Talos shutdown failed; host reboot NOT authorized; preserve this manifest"
  done

  deadline=$((SECONDS + 300))
  running=3
  while ((SECONDS < deadline)); do
    running="$(
      midclt_bounded vm.query |
        jq '[.[] | select(
          (.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02") and
          (.status.state // "UNKNOWN") != "STOPPED"
        )] | length'
    )"
    ((running == 0)) && break
    sleep 5
  done
  ((running == 0)) || fail "Talos VMs did not all reach STOPPED; preserve this manifest"

  printf 'PREPARED\n' >"${state_dir}/phase"
  record_prepare_history "${state_dir}" "prepared"
  printf '\nSUCCESS: homelab is prepared for TrueNAS reboot.\n'
  printf 'State manifest: %s\n' "${state_dir}"
  printf 'Now retry any proven CSI orphan with supported middleware deletion before reboot.\n'
  printf 'Then reboot TrueNAS through the TrueNAS UI or supported system.reboot API.\n'
  printf 'After boot, run this script with --post-reboot-check, then --resume.\n'
}

verify_bundle_integrity

if [[ "${MODE}" == "--check" ]]; then
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' EXIT
  midclt_bounded app.query >"${tmp}/apps-before.json"
  make_plans "${tmp}/apps-before.json" "${tmp}"
  vm_policy_gate
  cluster_client_preflight
  print_plan_summary "${tmp}"
  printf '\nREAD-ONLY: reboot orchestration preflight passed; no App or VM was changed.\n'
  exit 0
fi

if [[ "${MODE}" == "--prepare" ]]; then
  truenas_ready || fail "TrueNAS system.ready is not true"
  vm_policy_gate
  cluster_client_preflight
  guard_no_incomplete_prepare

  mkdir -p "${STATE_ROOT}"
  chmod 700 "${STATE_ROOT}"
  stamp="$(date +%Y%m%d-%H%M%S)"
  boot_id="$(midclt_bounded system.boot_id | tr -d '"')"
  state_dir="${STATE_ROOT}/${stamp}-${boot_id}"
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
    awk 'BEGIN { RS="[,[:space:]]+" } NF { print }' |
    sort -u >"${state_dir}/explicit-resume.txt"
  jq -r '.[] | select(.state=="STOPPED") | .id' "${state_dir}/apps-before.json" |
    sort -u |
    grep -Fvx -f "${state_dir}/explicit-resume.txt" >"${state_dir}/intentional-stopped.txt" || true
  jq -r '.[] | select(.state=="CRASHED" or .state=="ERROR") | .id' \
    "${state_dir}/apps-before.json" | sort -u >"${state_dir}/preexisting-failed.txt"
  jq -r '.selected_apps[]' "${state_dir}/resume-plan.json" >"${state_dir}/resume-apps.txt"
  bundle_identity >"${state_dir}/orchestrator-identity.txt"
  printf 'PREPARING\n' >"${state_dir}/phase"
  record_prepare_history "${state_dir}" "prepare"
  printf '%s\n' "${state_dir}" >"${STATE_ROOT}/latest"
  print_plan_summary "${state_dir}"

  continue_prepare "${state_dir}"
  exit 0
fi

if [[ "${MODE}" == "--continue-prepare" ]]; then
  truenas_ready || fail "TrueNAS system.ready is not true"
  state_dir="$(latest_state_dir)"
  validate_prepare_manifest "${state_dir}"

  before_boot_id="$(cat "${state_dir}/boot-id-before")"
  current_boot_id="$(midclt_bounded system.boot_id | tr -d '"')"
  [[ "${current_boot_id}" == "${before_boot_id}" ]] ||
    fail "boot_id changed; refusing to continue a pre-reboot manifest after reboot"

  phase="$(cat "${state_dir}/phase" 2>/dev/null || true)"
  case "${phase}" in
    PREPARING | "")
      ;;
    PREPARED)
      fail "manifest is already PREPARED; reboot through the supported TrueNAS UI/API instead"
      ;;
    *)
      fail "manifest phase=${phase:-missing} cannot be continued safely"
      ;;
  esac

  if [[ -z "${phase}" ]]; then
    warn "legacy interrupted prepare has no phase marker; manifest validation passed and will be adopted as PREPARING"
  fi

  printf 'Continuing preserved reboot manifest: %s\n' "${state_dir}"
  print_plan_summary "${state_dir}"
  continue_prepare "${state_dir}"
  exit 0
fi

state_dir="$(latest_state_dir)"
before_boot_id="$(cat "${state_dir}/boot-id-before")"
current_boot_id="$(midclt_bounded system.boot_id | tr -d '"')"

if [[ "${MODE}" == "--post-reboot-check" ]]; then
  [[ "${current_boot_id}" != "${before_boot_id}" ]] ||
    fail "boot_id did not change; no reboot has occurred since --prepare"
  truenas_ready || fail "TrueNAS has not completed boot"

  [[ -f "${IPAM_CHECK}" ]] || fail "IPAM post-reboot helper not found: ${IPAM_CHECK}"
  bash "${IPAM_CHECK}" --post-reboot-check

  vm_payload="$(midclt_bounded vm.query)"
  for name in "${VM_NAMES[@]}"; do
    jq -e --arg name "${name}" '
      [.[] | select(
        .name == $name and
        .autostart == true and
        (.status.state // "UNKNOWN") == "RUNNING"
      )] | length == 1
    ' <<<"${vm_payload}" >/dev/null ||
      fail "${name}: expected autostart=true and RUNNING after reboot"
  done

  for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
    talos_api_check "${node}" 60 post-reboot ||
      fail "Talos API not ready after reboot: ${node} via endpoint ${TALOS_ENDPOINT}"
  done
  run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=5m
  run_operator "${KUBECTL}" get nodes -o wide
  printf 'SUCCESS: TrueNAS, IPAM, Talos VM autostart and Kubernetes readiness passed post-reboot.\n'
  printf 'Next: --resume starts only Apps saved in the persistent resume manifest.\n'
  exit 0
fi

if [[ "${MODE}" == "--resume" ]]; then
  [[ "${current_boot_id}" != "${before_boot_id}" ]] || fail "refusing resume before an actual reboot"
  truenas_ready || fail "TrueNAS is not ready"

  run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=5m
  mapfile -t nodes < <(run_operator "${KUBECTL}" get nodes -o name)
  for node in "${nodes[@]}"; do
    run_operator "${KUBECTL}" uncordon "${node}" >/dev/null 2>&1 || true
  done
  run_operator "${KUBECTL}" get nodes

  printf '\nStarting saved Apps in topology dependency order...\n'
  wave_count="$(jq '.start_waves | length' "${state_dir}/resume-plan.json")"
  for ((i=0; i<wave_count; i++)); do
    printf 'START WAVE %s/%s\n' "$((i+1))" "${wave_count}"
    mapfile -t wave < <(jq -r --argjson i "${i}" '.start_waves[$i][]' \
      "${state_dir}/resume-plan.json")
    for app in "${wave[@]}"; do
      state="$(app_state "${app}")"
      if [[ "${state}" == "RUNNING" ]]; then
        printf 'SKIP %s already RUNNING\n' "${app}"
        continue
      fi
      [[ "${state}" == "STOPPED" ]] ||
        fail "${app}: expected STOPPED before resume, got ${state}; diagnose rather than redeploy"
      printf 'START %s\n' "${app}"
      midclt_bounded -j app.start "${app}" >/dev/null ||
        fail "${app}: app.start failed/timed out"
      wait_app_running "${app}"
    done
  done
  printf 'RESUMED\n' >"${state_dir}/phase"
  printf 'SUCCESS: saved pre-reboot active Apps resumed. Other STOPPED/CRASHED Apps were not auto-started.\n'
  exit 0
fi

# --verify
[[ "${current_boot_id}" != "${before_boot_id}" ]] || fail "reboot not observed"
truenas_ready || fail "TrueNAS is not ready"

failures=0
while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  state="$(app_state "${app}")"
  if [[ "${state}" != "RUNNING" ]]; then
    printf 'FAIL resume app %s state=%s expected=RUNNING\n' "${app}" "${state}" >&2
    failures=$((failures + 1))
  fi
done <"${state_dir}/resume-apps.txt"

while IFS= read -r app; do
  [[ -n "${app}" ]] || continue
  state="$(app_state "${app}")"
  if [[ "${state}" != "STOPPED" ]]; then
    printf 'WARN intentional pre-reboot STOPPED app %s is now %s\n' "${app}" "${state}" >&2
  fi
done <"${state_dir}/intentional-stopped.txt"

vm_policy_gate
run_operator "${KUBECTL}" wait --for=condition=Ready node --all --timeout=60s
((failures == 0)) || fail "${failures} saved Apps failed final RUNNING acceptance"
printf 'SUCCESS: homelab reboot lifecycle acceptance passed.\n'