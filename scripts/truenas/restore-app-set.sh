#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${NABLA_REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
PLANNER="${NABLA_REBOOT_PLANNER:-${SCRIPT_DIR}/plan-app-lifecycle-order.py}"
RECONCILER="${NABLA_REBOOT_RESUME_RECONCILER:-${SCRIPT_DIR}/reconcile-reboot-resume.sh}"
HEALTH_GATE="${NABLA_APP_HEALTH_GATE:-${SCRIPT_DIR}/verify-app-runtime-health.sh}"

MODE="--plan"
RECOVERY_DIR="${NABLA_RECOVERY_DIR:-}"
APPS_FILE=""
APPS_INLINE=""
LABEL="reviewed"

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/restore-app-set.sh --plan  --recovery-dir DIR (--apps-file FILE | --apps "a b c") [--label NAME]
  sudo bash scripts/truenas/restore-app-set.sh --check --recovery-dir DIR (--apps-file FILE | --apps "a b c") [--label NAME]
  sudo bash scripts/truenas/restore-app-set.sh --apply --recovery-dir DIR (--apps-file FILE | --apps "a b c") [--label NAME]

Purpose:
  Safely materialize a reviewed TrueNAS App restore set into a topology-aware
  resume plan, then delegate lifecycle handling to reconcile-reboot-resume.sh.

Modes:
  --plan   Build/reuse the reviewed plan and print waves without starting Apps.
  --check  Compare the reviewed plan with live App/runtime state (read-only).
  --apply  Start/verify Apps in topology waves; later waves block on failures.

Notes:
  - Membership is always explicit. This helper never infers "should start" from
    catalog operational-state, because active catalog intent is not boot intent.
  - The recovery snapshot remains authoritative for App identity.
  - Existing transactions are reused only if their frozen plan is identical.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --plan|--check|--apply)
      MODE="$1"
      shift
      ;;
    --recovery-dir)
      (($# >= 2)) || fail "--recovery-dir requires a value"
      RECOVERY_DIR="$2"
      shift 2
      ;;
    --apps-file)
      (($# >= 2)) || fail "--apps-file requires a value"
      APPS_FILE="$2"
      shift 2
      ;;
    --apps)
      (($# >= 2)) || fail "--apps requires a value"
      APPS_INLINE="$2"
      shift 2
      ;;
    --label)
      (($# >= 2)) || fail "--label requires a value"
      LABEL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$(id -u)" == "0" ]] || fail "run as root"
[[ -n "${RECOVERY_DIR}" ]] || fail "--recovery-dir is required"
[[ -d "${RECOVERY_DIR}" ]] || fail "recovery directory not found: ${RECOVERY_DIR}"
[[ "${LABEL}" =~ ^[a-zA-Z0-9._-]+$ ]] || fail "invalid label: ${LABEL}"
[[ -f "${PLANNER}" ]] || fail "planner not found: ${PLANNER}"
[[ -f "${RECONCILER}" ]] || fail "reconciler not found: ${RECONCILER}"
[[ -f "${HEALTH_GATE}" ]] || fail "health gate not found: ${HEALTH_GATE}"

if [[ -n "${APPS_FILE}" && -n "${APPS_INLINE}" ]]; then
  fail "use only one of --apps-file or --apps"
fi
if [[ -z "${APPS_FILE}" && -z "${APPS_INLINE}" ]]; then
  fail "one of --apps-file or --apps is required"
fi
if [[ -n "${APPS_FILE}" && ! -r "${APPS_FILE}" ]]; then
  fail "apps file not readable: ${APPS_FILE}"
fi

SNAPSHOT="${RECOVERY_DIR}/apps-before-cleanup.json"
[[ -r "${SNAPSHOT}" ]] || fail "recovery snapshot missing: ${SNAPSHOT}"

declare -a apps=()
if [[ -n "${APPS_FILE}" ]]; then
  mapfile -t apps < <(
    awk '
      /^[[:space:]]*#/ {next}
      NF {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
        if ($0 != "") print $0
      }
    ' "${APPS_FILE}" | sort -u
  )
else
  mapfile -t apps < <(
    tr ', ' '\n\n' <<<"${APPS_INLINE}" |
      awk 'NF && $1 !~ /^#/ {print $1}' |
      sort -u
  )
fi

(("${#apps[@]}" > 0)) || fail "reviewed App set is empty"

for app in "${apps[@]}"; do
  jq -e --arg app "${app}" '[.[] | select(.id == $app)] | length == 1'     "${SNAPSHOT}" >/dev/null ||
    fail "${app}: not found exactly once in frozen recovery snapshot"
done

include_apps="${apps[*]}"
PLAN="${RECOVERY_DIR}/restore-${LABEL}-plan.json"
PLAN_TMP="${PLAN}.tmp.$$"

python3 "${PLANNER}"   --apps "${SNAPSHOT}"   --states __NONE__   --include-apps "${include_apps}"   --services "${REPO_ROOT}/catalog/services.json"   --topology "${REPO_ROOT}/catalog/service-topology.json"   --pretty >"${PLAN_TMP}"

jq -e '.selected_apps | length > 0' "${PLAN_TMP}" >/dev/null ||
  fail "planner produced an empty selected App set"

if jq -e '.unmapped_apps | length > 0' "${PLAN_TMP}" >/dev/null; then
  jq '{unmapped_apps}' "${PLAN_TMP}" >&2
  rm -f "${PLAN_TMP}"
  fail "reviewed restore set contains unmapped Apps; update topology before automatic restore"
fi

mv "${PLAN_TMP}" "${PLAN}"

printf 'Restore set label=%s recovery=%s\n' "${LABEL}" "${RECOVERY_DIR}"
jq '{
  selected_apps,
  start_wave_phases,
  start_waves,
  required_edges
}' "${PLAN}"

if [[ "${MODE}" == "--plan" ]]; then
  printf 'PLAN ONLY: no App state was changed.\n'
  exit 0
fi

boot_file=""
for candidate in   "${RECOVERY_DIR}/boot-id-final-before-reboot.txt"   "${RECOVERY_DIR}/boot-id-before-recovery-reboot.txt"   "${RECOVERY_DIR}/boot-id-before"   "${RECOVERY_DIR}/boot-id.txt"; do
  if [[ -r "${candidate}" ]]; then
    boot_file="${candidate}"
    break
  fi
done
[[ -n "${boot_file}" ]] ||
  fail "no pre-reboot boot-id file found in ${RECOVERY_DIR}"

before_boot_id="$(tr -d '"[:space:]' <"${boot_file}")"
current_boot_id="$(midclt call system.boot_id | tr -d '"[:space:]')"
[[ -n "${before_boot_id}" ]] || fail "empty pre-reboot boot ID"
[[ "${before_boot_id}" != "${current_boot_id}" ]] ||
  fail "current boot ID equals frozen pre-reboot ID; refusing restore"

ROOT="${RECOVERY_DIR}/reconcile-${LABEL}"
TXN="${ROOT}/txn"
install -d -m 700 "${ROOT}" "${TXN}"

if [[ -f "${TXN}/resume-plan.json" ]]; then
  cmp -s "${PLAN}" "${TXN}/resume-plan.json" ||
    fail "existing ${LABEL} transaction has a different frozen plan; choose a new label"
else
  cp "${PLAN}" "${TXN}/resume-plan.json"
fi

if [[ -f "${TXN}/apps-before.json" ]]; then
  cmp -s "${SNAPSHOT}" "${TXN}/apps-before.json" ||
    fail "existing ${LABEL} transaction has a different frozen snapshot"
else
  cp -p "${SNAPSHOT}" "${TXN}/apps-before.json"
fi

if [[ -f "${TXN}/boot-id-before" ]]; then
  [[ "$(tr -d '"[:space:]' <"${TXN}/boot-id-before")" == "${before_boot_id}" ]] ||
    fail "existing ${LABEL} transaction has a different boot ID"
else
  printf '%s\n' "${before_boot_id}" >"${TXN}/boot-id-before"
fi

printf '%s\n' "${TXN}" >"${ROOT}/latest"

printf 'Delegating to topology-aware reconciler: mode=%s transaction=%s\n'   "${MODE}" "${TXN}"

exec env   NABLA_REBOOT_STATE_ROOT="${ROOT}"   NABLA_APP_HEALTH_GATE="${HEALTH_GATE}"   "${RECONCILER}" "${MODE}"
