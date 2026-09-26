#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---status}"
STATE_ROOT="${NABLA_RECOVERY_STATE_ROOT:-/mnt/cpool/var/nabla/recovery}"
STATE_DIR="${NABLA_RECOVERY_DIR:-}"
REPO_ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
OPERATOR_USER="${NABLA_K8S_OPERATOR_USER:-albandrieu}"
CALL_TIMEOUT="${NABLA_MIDCLT_TIMEOUT_SECONDS:-180}"
APP_JOB_TIMEOUT="${NABLA_APP_JOB_TIMEOUT_SECONDS:-900}"
POST_BOOT_DOCKER_WAIT="${NABLA_RECOVERY_DOCKER_WAIT_SECONDS:-900}"
VM_WAIT="${NABLA_RECOVERY_VM_WAIT_SECONDS:-600}"
TALOS_API_WAIT="${NABLA_RECOVERY_TALOS_API_WAIT_SECONDS:-600}"
K8S_WAIT="${NABLA_RECOVERY_K8S_WAIT_SECONDS:-600}"
POLL_SECONDS="${NABLA_RECOVERY_POLL_SECONDS:-5}"
TALOS_WAIT="${NABLA_TALOS_SHUTDOWN_TIMEOUT:-15m}"
TALOS_ENDPOINT="${NABLA_TALOS_ENDPOINT:-172.17.0.50}"
TALOS_NODES=(172.17.0.51 172.17.0.52 172.17.0.50)
VM_NAMES=(taloscp01 taloswk01 taloswk02)

PLANNER="${NABLA_REBOOT_PLANNER:-${SCRIPT_DIR}/plan-app-lifecycle-order.py}"
GHOST_RECOVERY="${NABLA_APP_GHOST_RECOVERY_HELPER:-${SCRIPT_DIR}/recover-app-after-docker-ghost.sh}"
ORPHAN_SHIMS="${NABLA_ORPHAN_SHIM_DIAGNOSTIC:-${SCRIPT_DIR}/diagnose-docker-orphan-shims.sh}"
IPAM_CHECK="${NABLA_IPAM_CHECK_SCRIPT:-${SCRIPT_DIR}/migrate-docker-address-pool.sh}"
RESUME_RECONCILER="${NABLA_REBOOT_RESUME_RECONCILER:-${SCRIPT_DIR}/reconcile-reboot-resume.sh}"
HEALTH_GATE="${NABLA_APP_HEALTH_GATE:-${SCRIPT_DIR}/verify-app-runtime-health.sh}"

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --prepare
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --continue
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --status
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --reboot
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --post-reboot-check
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --resume-safe
  sudo bash scripts/truenas/recovery-reboot-homelab.sh --resume-reviewed

This is the recovery path for a stale/missing normal reboot manifest or widespread
Docker/containerd ghost state. Normal planned maintenance should continue to use
reboot-homelab.sh.

--prepare
  Snapshot current intent, quiesce all Apps with bounded App-scoped ghost repair,
  gracefully stop Talos workers then control-plane, and stop at READY_TO_REBOOT.

--continue
  Resume an interrupted recovery transaction from its persisted phase.

--reboot
  Revalidate zero-running Docker, zero ghost state, all Apps STOPPED and all
  Talos VMs STOPPED/autostart=true, then invoke supported TrueNAS system.reboot.

--post-reboot-check
  Require a changed boot ID, healthy Docker/IPAM, no automatically resurrected
  Apps, Talos VMs autostarted, Talos APIs reachable and Kubernetes Ready.

--resume-safe
  Resume only Apps that were RUNNING/DEPLOYING in the recovery snapshot.

--resume-reviewed
  Resume only Apps listed in <state-dir>/resume-approved.txt. Every approved App
  must belong to resume-review.txt, which also includes CRASHED/ERROR snapshot
  states for explicit operator review.
EOF
}

case "${MODE}" in
  --prepare | --continue | --status | --reboot | --post-reboot-check | --resume-safe | --resume-reviewed) ;;
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
require_commands midclt jq docker python3 timeout getent awk tr sort grep install date systemctl
for value in POST_BOOT_DOCKER_WAIT VM_WAIT TALOS_API_WAIT K8S_WAIT POLL_SECONDS; do
  current="${!value}"
  [[ "${current}" =~ ^[1-9][0-9]*$ ]] || fail "${value} must be a positive integer"
done
for path in "${PLANNER}" "${GHOST_RECOVERY}" "${ORPHAN_SHIMS}" "${IPAM_CHECK}" "${RESUME_RECONCILER}" "${HEALTH_GATE}"; do
  [[ -f "${path}" ]] || fail "required recovery helper not found: ${path}"
done
[[ -f "${REPO_ROOT}/catalog/services.json" ]] || fail "services catalog missing under ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/catalog/service-topology.json" ]] || fail "topology catalog missing under ${REPO_ROOT}"

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
  else
    sudo -u "${OPERATOR_USER}" env \
      HOME="${operator_home}" \
      PATH="/mnt/cpool/tools/bin:/usr/bin:/bin" \
      TALOSCONFIG="${TALOSCONFIG}" \
      KUBECONFIG="${KUBECONFIG}" \
      "$@"
  fi
}

midclt_bounded() {
  timeout "${CALL_TIMEOUT}" midclt call "$@"
}

current_boot_id() {
  midclt_bounded system.boot_id | tr -d '"'
}

truenas_ready() {
  local raw
  raw="$(midclt_bounded system.ready | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  [[ "${raw}" == "true" ]]
}

app_state() {
  local app="$1"
  midclt_bounded app.query "[[\"id\",\"=\",\"${app}\"]]" |
    jq -r 'if length == 1 then .[0].state else "MISSING" end'
}

all_apps_stopped() {
  midclt_bounded app.query |
    jq -e 'length > 0 and all(.[]; .state == "STOPPED")' >/dev/null
}

ghost_apps() {
  bash "${GHOST_RECOVERY}" --check |
    awk -F '\t' 'NR > 1 && $1 != "" {print $1}' |
    sort -u
}

ghost_count() {
  local count
  count="$(ghost_apps | awk 'NF {count++} END {print count+0}')"
  printf '%s\n' "${count}"
}

docker_zero_gate() {
  local -a running=()
  mapfile -t running < <(docker ps --format '{{.Names}}')
  if (("${#running[@]}" > 0)); then
    printf 'Running Docker containers:\n  %s\n' "${running[*]}" >&2
    return 1
  fi
  [[ "$(ghost_count)" == "0" ]]
}

vm_payload() {
  midclt_bounded vm.query
}

vm_state() {
  local name="$1"
  vm_payload |
    jq -r --arg name "${name}" '
      [.[] | select(.name == $name)]
      | if length == 1 then .[0].status.state // "UNKNOWN" else "UNKNOWN" end
    '
}

vm_name_for_node() {
  case "$1" in
    172.17.0.50) printf 'taloscp01\n' ;;
    172.17.0.51) printf 'taloswk01\n' ;;
    172.17.0.52) printf 'taloswk02\n' ;;
    *) fail "unknown Talos node address: $1" ;;
  esac
}

vm_policy_gate() {
  local payload name row timeout_seconds
  payload="$(vm_payload)"
  for name in "${VM_NAMES[@]}"; do
    row="$(
      jq -ce --arg name "${name}" '
        [.[] | select(.name == $name)]
        | if length == 1 then .[0] else error("VM count mismatch") end
      ' <<<"${payload}"
    )" || fail "unable to resolve ${name}"
    [[ "$(jq -r '.autostart' <<<"${row}")" == "true" ]] ||
      fail "${name}: autostart=false"
    timeout_seconds="$(jq -r '.shutdown_timeout // 0' <<<"${row}")"
    ((timeout_seconds >= 120)) ||
      fail "${name}: shutdown_timeout=${timeout_seconds}s; require >=120s"
  done
}

all_talos_vms_in_state() {
  local expected="$1" payload
  payload="$(vm_payload)"
  jq -e --arg expected "${expected}" '
    [
      .[]
      | select(.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02")
      | (.status.state // "UNKNOWN")
    ] as $states
    | ($states | length) == 3 and all($states[]; . == $expected)
  ' <<<"${payload}" >/dev/null
}

talos_vm_summary() {
  vm_payload |
    jq -c '[
      .[]
      | select(.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02")
      | {name,state:(.status.state // "UNKNOWN"),autostart}
    ] | sort_by(.name)'
}

wait_talos_vms_running() {
  local deadline summary last=""
  deadline=$((SECONDS + VM_WAIT))
  while ((SECONDS < deadline)); do
    summary="$(talos_vm_summary)"
    if [[ "${summary}" != "${last}" ]]; then
      printf '  Talos VM convergence: %s\n' "${summary}"
      last="${summary}"
    fi
    if jq -e       'length==3 and all(.[]; .autostart==true and .state=="RUNNING")'       <<<"${summary}" >/dev/null; then
      return 0
    fi
    sleep "${POLL_SECONDS}"
  done

  printf 'Talos VM state after timeout:\n' >&2
  talos_vm_summary | jq . >&2
  fail "Talos VMs did not all become RUNNING within ${VM_WAIT}s"
}

wait_talos_apis() {
  local node deadline ready
  for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
    deadline=$((SECONDS + TALOS_API_WAIT))
    ready=0
    printf 'Waiting for Talos API node=%s endpoint=%s...\n'       "${node}" "${TALOS_ENDPOINT}"
    while ((SECONDS < deadline)); do
      if run_operator timeout 15 "${TALOSCTL}"         --endpoints "${TALOS_ENDPOINT}"         --nodes "${node}" version >/dev/null 2>&1; then
        ready=1
        printf '  Talos API ready: %s\n' "${node}"
        break
      fi
      sleep "${POLL_SECONDS}"
    done
    ((ready == 1)) ||
      fail "Talos API did not become ready for ${node} within ${TALOS_API_WAIT}s"
  done
}

latest_state_dir() {
  [[ -f "${STATE_ROOT}/latest" ]] || fail "no recovery transaction at ${STATE_ROOT}/latest"
  local dir
  dir="$(cat "${STATE_ROOT}/latest")"
  [[ -d "${dir}" ]] || fail "recovery state directory missing: ${dir}"
  printf '%s\n' "${dir}"
}

resolve_state_dir() {
  if [[ -n "${STATE_DIR}" ]]; then
    [[ -d "${STATE_DIR}" ]] || fail "NABLA_RECOVERY_DIR does not exist: ${STATE_DIR}"
  else
    STATE_DIR="$(latest_state_dir)"
  fi
}

phase() {
  cat "${STATE_DIR}/phase" 2>/dev/null || printf 'UNKNOWN\n'
}

write_phase() {
  printf '%s\n' "$1" >"${STATE_DIR}/phase"
  printf '%s phase=%s\n' "$(date -Iseconds)" "$1" >>"${STATE_DIR}/history.log"
}

create_snapshot() {
  local boot stamp dir
  boot="$(current_boot_id)"
  stamp="$(date +%Y%m%d-%H%M%S)"
  dir="${STATE_ROOT}/${stamp}-${boot}"

  install -d -m 700 "${STATE_ROOT}" "${dir}"
  [[ ! -e "${STATE_ROOT}/latest" ]] || {
    local previous previous_boot previous_phase
    previous="$(cat "${STATE_ROOT}/latest" 2>/dev/null || true)"
    if [[ -d "${previous}" && -f "${previous}/boot-id-before" ]]; then
      previous_boot="$(cat "${previous}/boot-id-before")"
      previous_phase="$(cat "${previous}/phase" 2>/dev/null || true)"
      if [[ "${previous_boot}" == "${boot}" && "${previous_phase}" != "COMPLETE" ]]; then
        fail "same-boot recovery transaction exists at ${previous} phase=${previous_phase:-UNKNOWN}; use --continue"
      fi
    fi
  }

  STATE_DIR="${dir}"
  printf '%s\n' "${boot}" >"${STATE_DIR}/boot-id-before"
  midclt_bounded app.query >"${STATE_DIR}/apps-before-cleanup.json"
  vm_payload >"${STATE_DIR}/talos-vms-before-shutdown.json"
  midclt_bounded docker.status >"${STATE_DIR}/docker-status-before.json"
  midclt_bounded docker.config >"${STATE_DIR}/docker-config-before.json"
  docker ps -a --format '{{.Names}}\t{{.Status}}' >"${STATE_DIR}/containers-before-cleanup.txt"

  jq -r '.[] | select(.state=="STOPPED") | .id'     "${STATE_DIR}/apps-before-cleanup.json" |
    sort -u >"${STATE_DIR}/intentional-stopped.txt"
  jq -r '.[] | select(.state=="RUNNING" or .state=="DEPLOYING") | .id'     "${STATE_DIR}/apps-before-cleanup.json" |
    sort -u >"${STATE_DIR}/resume-safe.txt"
  jq -r '
    .[]
    | select(.state=="RUNNING" or .state=="DEPLOYING" or .state=="CRASHED" or .state=="ERROR")
    | .id
  ' "${STATE_DIR}/apps-before-cleanup.json" |
    sort -u >"${STATE_DIR}/resume-review.txt"

  python3 "${PLANNER}"     --apps "${STATE_DIR}/apps-before-cleanup.json"     --states RUNNING,DEPLOYING,CRASHED,ERROR,STOPPING     --services "${REPO_ROOT}/catalog/services.json"     --topology "${REPO_ROOT}/catalog/service-topology.json"     --pretty >"${STATE_DIR}/shutdown-plan.json"

  python3 "${PLANNER}"     --apps "${STATE_DIR}/apps-before-cleanup.json"     --states RUNNING,DEPLOYING     --services "${REPO_ROOT}/catalog/services.json"     --topology "${REPO_ROOT}/catalog/service-topology.json"     --pretty >"${STATE_DIR}/resume-safe-plan.json"

  write_phase SNAPSHOT
  printf '%s\n' "${STATE_DIR}" >"${STATE_ROOT}/latest"
  ok "recovery snapshot created: ${STATE_DIR}"
}

recover_app_for_quiesce() {
  local app="$1" state
  state="$(app_state "${app}")"
  case "${state}" in
    RUNNING | DEPLOYING)
      NABLA_GHOST_RECOVERY_ALLOW_ACTIVE=true         bash "${GHOST_RECOVERY}" --recover-app "${app}"
      ;;
    STOPPED | CRASHED | ERROR)
      bash "${GHOST_RECOVERY}" --recover-app "${app}"
      ;;
    *)
      fail "${app}: unsupported state during recovery quiesce: ${state}"
      ;;
  esac
}

quiesce_apps() {
  local app
  local -a apps=() ghosts=()
  write_phase QUIESCING

  mapfile -t apps < <(jq -r '.stop_order[]' "${STATE_DIR}/shutdown-plan.json")
  for app in "${apps[@]}"; do
    printf '\n=== QUIESCE %s ===\n' "${app}"
    recover_app_for_quiesce "${app}"
  done

  # STOPPED Apps can still own Docker ghosts after a failed boot. Repair those
  # after the topology-ordered stop pass.
  mapfile -t ghosts < <(ghost_apps)
  for app in "${ghosts[@]}"; do
    [[ -n "${app}" ]] || continue
    printf '\n=== CLEAN STOPPED/RESIDUAL GHOST APP %s ===\n' "${app}"
    recover_app_for_quiesce "${app}"
  done

  midclt_bounded app.query >"${STATE_DIR}/apps-after-quiesce.json"
  docker ps -a --format '{{.Names}}\t{{.Status}}' >"${STATE_DIR}/containers-after-quiesce.txt"
  bash "${ORPHAN_SHIMS}" --check >"${STATE_DIR}/orphan-check-after-quiesce.txt"

  all_apps_stopped || fail "not all TrueNAS Apps converged to STOPPED"
  docker_zero_gate || fail "Docker zero-running/zero-ghost gate failed after App quiesce"

  write_phase QUIESCED
  ok "all TrueNAS Apps STOPPED; Docker zero-running/zero-ghost gate passed"
}

shutdown_talos() {
  local cp_state node name state deadline remaining
  local payload

  all_apps_stopped || fail "refusing Talos shutdown while an App is not STOPPED"
  docker_zero_gate || fail "refusing Talos shutdown while Docker is not quiesced"
  vm_policy_gate

  if all_talos_vms_in_state STOPPED; then
    vm_payload >"${STATE_DIR}/talos-vms-after-shutdown.json"
    write_phase READY_TO_REBOOT
    ok "Talos VMs were already STOPPED"
    return 0
  fi

  cp_state="$(vm_state taloscp01)"
  [[ "${cp_state}" == "RUNNING" ]] ||
    fail "taloscp01 is ${cp_state} while Talos is not fully STOPPED; restore control-plane before continuing"

  payload="$(vm_payload)"
  if jq -e '
    [
      .[]
      | select(.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02")
      | (.status.state // "UNKNOWN")
    ]
    | all(.[]; .=="RUNNING")
  ' <<<"${payload}" >/dev/null; then
    run_operator "${KUBECTL}" get nodes -o wide
    for node in 172.17.0.50 172.17.0.51 172.17.0.52; do
      run_operator timeout 30 "${TALOSCTL}"         --endpoints "${TALOS_ENDPOINT}"         --nodes "${node}" version >/dev/null ||
        fail "Talos API preflight failed for ${node}"
    done
  else
    warn "continuing partial Talos shutdown with control-plane still RUNNING"
  fi

  write_phase SHUTTING_DOWN_TALOS
  for node in "${TALOS_NODES[@]}"; do
    name="$(vm_name_for_node "${node}")"
    state="$(vm_state "${name}")"
    if [[ "${state}" == "STOPPED" ]]; then
      printf 'SKIP %s (%s) already STOPPED\n' "${name}" "${node}"
      continue
    fi
    [[ "${state}" == "RUNNING" ]] ||
      fail "${name}: unexpected VM state=${state}"
    printf 'SHUTDOWN %s (%s)\n' "${name}" "${node}"
    run_operator timeout 20m "${TALOSCTL}"       --endpoints "${TALOS_ENDPOINT}"       --nodes "${node}"       shutdown --wait --timeout "${TALOS_WAIT}" ||
      fail "${name}: graceful Talos shutdown failed"
  done

  deadline=$((SECONDS + 300))
  remaining=3
  while ((SECONDS < deadline)); do
    if all_talos_vms_in_state STOPPED; then
      remaining=0
      break
    fi
    sleep 5
  done
  ((remaining == 0)) || fail "Talos VMs did not all reach STOPPED"

  vm_payload >"${STATE_DIR}/talos-vms-after-shutdown.json"
  write_phase READY_TO_REBOOT
  ok "Talos workers/control-plane STOPPED with autostart policy preserved"
}

continue_prepare() {
  local current_phase
  current_phase="$(phase)"
  case "${current_phase}" in
    SNAPSHOT | QUIESCING)
      quiesce_apps
      shutdown_talos
      ;;
    QUIESCED | SHUTTING_DOWN_TALOS)
      shutdown_talos
      ;;
    READY_TO_REBOOT)
      ok "recovery transaction already READY_TO_REBOOT: ${STATE_DIR}"
      ;;
    *)
      fail "cannot continue recovery transaction from phase=${current_phase}"
      ;;
  esac
}

reboot_gate() {
  local before now
  [[ "$(phase)" == "READY_TO_REBOOT" ]] ||
    fail "recovery phase must be READY_TO_REBOOT"
  before="$(cat "${STATE_DIR}/boot-id-before")"
  now="$(current_boot_id)"
  [[ "${now}" == "${before}" ]] ||
    fail "boot already changed; use --post-reboot-check"
  all_apps_stopped || fail "an App is no longer STOPPED"
  docker_zero_gate || fail "Docker zero-running/zero-ghost gate no longer passes"
  vm_policy_gate
  all_talos_vms_in_state STOPPED || fail "all Talos VMs must be STOPPED before host reboot"

  date -Iseconds >"${STATE_DIR}/reboot-authorized-at.txt"
  printf '%s\n' "${now}" >"${STATE_DIR}/boot-id-final-before-reboot.txt"
}

post_reboot_check() {
  local before now status name payload
  [[ "$(phase)" == "READY_TO_REBOOT" ]] ||
    fail "expected READY_TO_REBOOT before post-reboot validation"
  before="$(cat "${STATE_DIR}/boot-id-before")"
  now="$(current_boot_id)"
  [[ "${now}" != "${before}" ]] || fail "boot ID did not change"
  truenas_ready || fail "TrueNAS system.ready is not true"
  printf 'Waiting for Docker/Apps initialization before post-reboot gates...\n'
  TRUENAS_DOCKER_POST_BOOT_WAIT_SECONDS="${POST_BOOT_DOCKER_WAIT}"     bash "${IPAM_CHECK}" --post-reboot-check

  [[ "$(systemctl is-active docker)" == "active" ]] ||
    fail "docker.service is not active after IPAM readiness gate"
  [[ "$(systemctl is-active containerd)" == "active" ]] ||
    fail "containerd.service is not active after IPAM readiness gate"
  status="$(midclt_bounded docker.status | jq -r '.status // empty')"
  [[ "${status}" == "RUNNING" ]] ||
    fail "TrueNAS docker.status=${status:-UNKNOWN} after IPAM readiness gate"

  midclt_bounded app.query >"${STATE_DIR}/apps-post-reboot.json"
  docker ps -a --format '{{.Names}}\t{{.Status}}' >"${STATE_DIR}/containers-post-reboot.txt"
  bash "${ORPHAN_SHIMS}" --check >"${STATE_DIR}/orphan-check-post-reboot.txt"

  all_apps_stopped ||
    fail "one or more Apps auto-resurrected after recovery reboot; inspect apps-post-reboot.json"
  docker_zero_gate ||
    fail "Docker containers/ghosts auto-resurrected after recovery reboot"

  vm_policy_gate
  printf 'Waiting for Talos VM autostart (timeout=%ss)...\n' "${VM_WAIT}"
  wait_talos_vms_running
  wait_talos_apis
  printf 'Waiting for Kubernetes nodes Ready (timeout=%ss)...\n' "${K8S_WAIT}"
  run_operator "${KUBECTL}" wait     --for=condition=Ready node --all --timeout="${K8S_WAIT}s" ||
    fail "Kubernetes nodes did not all become Ready within ${K8S_WAIT}s"
  run_operator "${KUBECTL}" get nodes -o wide

  printf '%s\n' "${now}" >"${STATE_DIR}/boot-id-after-reboot.txt"
  write_phase POST_REBOOT_READY
  ok "post-reboot infrastructure gate passed; Apps remain intentionally STOPPED"
}

run_resume_plan() {
  local plan="$1" label="$2" root txn
  [[ -f "${plan}" ]] || fail "resume plan not found: ${plan}"
  root="${STATE_DIR}/reconcile-${label}"
  txn="${root}/txn"
  rm -rf "${root}"
  install -d -m 700 "${txn}"
  cp -p "${STATE_DIR}/apps-before-cleanup.json" "${txn}/apps-before.json"
  cp "${plan}" "${txn}/resume-plan.json"
  cp "${STATE_DIR}/boot-id-before" "${txn}/boot-id-before"
  printf '%s\n' "${txn}" >"${root}/latest"

  NABLA_REBOOT_STATE_ROOT="${root}"     NABLA_APP_HEALTH_GATE="${HEALTH_GATE}"     bash "${RESUME_RECONCILER}" --apply
}

resume_safe() {
  [[ "$(phase)" == "POST_REBOOT_READY" || "$(phase)" == "RESUMED_SAFE" ]] ||
    fail "--resume-safe requires POST_REBOOT_READY"
  run_resume_plan "${STATE_DIR}/resume-safe-plan.json" safe
  write_phase RESUMED_SAFE
  ok "safe recovery resume completed"
}

resume_reviewed() {
  local approved_file="${STATE_DIR}/resume-approved.txt" app approved
  local -a approved_apps=()

  case "$(phase)" in
    POST_REBOOT_READY | RESUMED_SAFE | RESUMED_REVIEWED) ;;
    *) fail "--resume-reviewed requires successful post-reboot infrastructure validation" ;;
  esac

  [[ -f "${approved_file}" ]] ||
    fail "reviewed resume file missing: ${approved_file}; create it from resume-review.txt"
  mapfile -t approved_apps < <(awk 'NF && $1 !~ /^#/ {print $1}' "${approved_file}" | sort -u)
  (("${#approved_apps[@]}" > 0)) || fail "resume-approved.txt contains no App IDs"

  for app in "${approved_apps[@]}"; do
    grep -Fxq -- "${app}" "${STATE_DIR}/resume-review.txt" ||
      fail "${app}: not present in frozen resume-review.txt candidate set"
  done
  approved="${approved_apps[*]}"

  python3 "${PLANNER}"     --apps "${STATE_DIR}/apps-before-cleanup.json"     --states __NONE__     --include-apps "${approved}"     --services "${REPO_ROOT}/catalog/services.json"     --topology "${REPO_ROOT}/catalog/service-topology.json"     --pretty >"${STATE_DIR}/resume-approved-plan.json"

  run_resume_plan "${STATE_DIR}/resume-approved-plan.json" reviewed
  write_phase RESUMED_REVIEWED
  ok "reviewed recovery resume completed"
}

show_status() {
  resolve_state_dir
  printf 'RECOVERY_DIR=%s\n' "${STATE_DIR}"
  printf 'phase=%s\n' "$(phase)"
  printf 'boot-before=%s\n' "$(cat "${STATE_DIR}/boot-id-before" 2>/dev/null || echo unknown)"
  printf 'boot-current=%s\n' "$(current_boot_id)"
  printf '\nApps:\n'
  midclt_bounded app.query |
    jq 'group_by(.state) | map({state:.[0].state,count:length})'
  printf '\nDocker running:\n'
  docker ps --format 'table {{.Names}}\t{{.Status}}'
  printf '\nDocker ghosts:\n'
  bash "${ORPHAN_SHIMS}" --check
  printf '\nTalos VMs:\n'
  vm_payload |
    jq '[
      .[]
      | select(.name=="taloscp01" or .name=="taloswk01" or .name=="taloswk02")
      | {name,state:(.status.state // "UNKNOWN"),autostart,shutdown_timeout}
    ]'
}

case "${MODE}" in
  --prepare)
    [[ -z "${STATE_DIR}" ]] ||
      fail "--prepare creates a new transaction; do not set NABLA_RECOVERY_DIR"
    create_snapshot
    quiesce_apps
    shutdown_talos
    ;;
  --continue)
    resolve_state_dir
    [[ "$(current_boot_id)" == "$(cat "${STATE_DIR}/boot-id-before")" ]] ||
      fail "boot already changed; use --post-reboot-check"
    continue_prepare
    ;;
  --status)
    show_status
    ;;
  --reboot)
    resolve_state_dir
    reboot_gate
    write_phase REBOOTING
    # Preserve READY_TO_REBOOT semantics if middleware returns instead of rebooting.
    printf 'READY_TO_REBOOT\n' >"${STATE_DIR}/phase"
    midclt call -j system.reboot       "Nabla recovery reboot after bounded Docker ghost cleanup and graceful Talos shutdown"       '{"delay": null}'
    ;;
  --post-reboot-check)
    resolve_state_dir
    post_reboot_check
    ;;
  --resume-safe)
    resolve_state_dir
    resume_safe
    ;;
  --resume-reviewed)
    resolve_state_dir
    resume_reviewed
    ;;
esac
