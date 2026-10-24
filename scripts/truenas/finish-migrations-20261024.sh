#!/usr/bin/env bash
# Temporary operator wrapper for the 2026-10-24 TrueNAS migration acceptance.
# Default: read-only diagnostics. NEVER reboots TrueNAS or mutates Apps implicitly.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${ROOT}"
# Reuse the shared terminal-aware colors/icons across operator diagnostics.
# ANSI is never written to the TSV report or private child logs.
# shellcheck source=../lib/diagnostic-ui.sh
source "${ROOT}/scripts/lib/diagnostic-ui.sh"
COLOR_MODE=auto
ICON_MODE=auto
VERBOSE=false
REPORT_ROOT="${NABLA_MIGRATION_REPORT_ROOT:-/mnt/cpool/var/nabla/migration-20261024}"
ACK_RESTART="I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART"
ACK_MIGRATION="I_ACCEPT_REVIEWED_RUNTIME_MIGRATION"

ACTION="check"
SECTION="all"
WAVE=""
STEP=""
HASH=""
ACK=""
ALLOW_DRIFT=false

usage() {
  cat <<'EOF'
Usage (TrueNAS, from /mnt/cpool/compose/nabla-compose):
  # FAST PARALLEL IMAGE REFRESH (after review/merge, separate from waves):
  # python3 scripts/truenas/fast-bulk-redeploy-apps.py --check --scope all --parallel 8
  # For the concurrent Talos/Kubernetes operator flow see
  # docs/runbooks/2026-10-23-fast-batch-migration.md

  bash scripts/truenas/finish-migrations-20261024.sh --next-commands
  bash scripts/truenas/finish-migrations-20261024.sh --local-gates
  sudo bash scripts/truenas/finish-migrations-20261024.sh --check [--section all|platform|migrations|catalog|services|ai|critical|prometheus|openrag|sentry|akvorado|defectdojo|talos|observability|secrets|convergence|lan] [--color auto|always|never] [--icons auto|always|never] [--verbose]
  sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave core|gatus|deferred
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-wave core|gatus|deferred \
    --expected-plan-hash <64-hex-from-plan> \
    --acknowledge I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-step \
    sentry-system|sentry-migrator|gatus-config \
    --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-csi-smoke \
    --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION

All modes write PRIVATE metadata/diagnostic logs under
/mnt/cpool/var/nabla/migration-20261024. Inspect the private logs before
proceeding. --check and --plan-wave never stop/start/redeploy Apps.
--apply-step runs its matching --check first; if drift makes the check fail,
review its report and repeat with --allow-reviewed-drift (explicit override).
--next-commands prints only the canonical runbook path; no document dump, no TrueNAS call.
The legacy OpenRAG/OpenSearch password reconciliation --apply is DISABLED
in this runner. Use Vaultwarden-backed canonical staging after a separate review.
No automatic remediation for DefectDojo, Docling, Hermes, OpenRAG ingestion,
Vaultwarden secret import or TrueNAS host reboot: see the runbook.
EOF
}

while (($#)); do
  case "$1" in
    --check) ACTION="check"; shift ;;
    --next-commands) ACTION="commands"; shift ;;
    --local-gates) ACTION="local-gates"; shift ;;
    --section) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; SECTION="$2"; shift 2 ;;
    --plan-wave) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="plan"; WAVE="$2"; shift 2 ;;
    --apply-wave) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="restart"; WAVE="$2"; shift 2 ;;
    --apply-step) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="migrate"; STEP="$2"; shift 2 ;;
    --apply-csi-smoke) ACTION="smoke"; shift ;;
    --expected-plan-hash) [[ $# -ge 2 ]] || exit 2; HASH="$2"; shift 2 ;;
    --acknowledge) [[ $# -ge 2 ]] || exit 2; ACK="$2"; shift 2 ;;
    --allow-reviewed-drift) ALLOW_DRIFT=true; shift ;;
    --color) [[ $# -ge 2 ]] || exit 2; COLOR_MODE="$2"; shift 2 ;;
    --color=*) COLOR_MODE="${1#*=}"; shift ;;
    --icons) [[ $# -ge 2 ]] || exit 2; ICON_MODE="$2"; shift 2 ;;
    --icons=*) ICON_MODE="${1#*=}"; shift ;;
    --verbose) VERBOSE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument (see --help): %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ "${ACTION}" == commands ]]; then
  [[ "${SECTION}" == all && -z "${WAVE}" && -z "${STEP}" &&
     -z "${HASH}" && -z "${ACK}" && "${ALLOW_DRIFT}" == false ]] || {
    echo '--next-commands accepts no apply, wave or section flags' >&2
    exit 2
  }
  RUNBOOK="${ROOT}/docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
  [[ -f "${RUNBOOK}" && ! -L "${RUNBOOK}" ]] || {
    echo 'Operator runbook unavailable; no commands executed' >&2
    exit 2
  }
  printf 'RUNBOOK=%s\n' "docs/runbooks/2026-10-24-homelab-operator-next-commands.md"
  exit 0
fi

if [[ "${ACTION}" == local-gates ]]; then
  [[ "${SECTION}" == all && -z "${WAVE}" && -z "${STEP}" &&
     -z "${HASH}" && -z "${ACK}" && "${ALLOW_DRIFT}" == false ]] || {
    echo '--local-gates accepts no apply, wave or section flags' >&2
    exit 2
  }
  (( EUID != 0 )) || { echo '--local-gates must run as non-root' >&2; exit 2; }
  command -v just >/dev/null 2>&1 || {
    echo 'just is required; no quality gate executed' >&2
    exit 2
  }
  # Explicit local-only runner; does not use midclt, Docker or GitHub Actions.
  for recipe in migration-20261024-commands migration-20261024-test \
                catalog-convergence-check agent-skills-check quality; do
    printf 'LOCAL_GATE_START=%s\n' "${recipe}"
    if just "${recipe}"; then
      printf 'LOCAL_GATE_PASS=%s\n' "${recipe}"
    else
      printf 'LOCAL_GATE_FAIL=%s; later gates skipped\n' "${recipe}" >&2
      exit 1
    fi
  done
  printf 'LOCAL_GATES_COMPLETE=5 (TrueNAS runtime not attested)\n'
  exit 0
fi

diag_ui_init "${COLOR_MODE}" "${ICON_MODE}" || exit 2
case "${ACTION}" in check|plan|restart|migrate|smoke) ;; *) exit 2 ;; esac
case "${SECTION}" in all|platform|migrations|catalog|services|ai|critical|prometheus|openrag|sentry|akvorado|defectdojo|talos|observability|secrets|convergence|lan) ;; *) echo 'Invalid section' >&2; exit 2 ;; esac
if [[ "${ACTION}" == plan || "${ACTION}" == restart ]]; then
  case "${WAVE}" in core|gatus|deferred) ;; *) echo 'Invalid wave' >&2; exit 2 ;; esac
fi
if [[ "${ACTION}" == migrate ]]; then
  case "${STEP}" in sentry-system|sentry-migrator|gatus-config) ;; *) echo 'Invalid migration step' >&2; exit 2 ;; esac
fi
if [[ "${ACTION}" != migrate && "${ALLOW_DRIFT}" == true ]]; then
  echo '--allow-reviewed-drift only applies to --apply-step' >&2
  exit 2
fi
if [[ "${ACTION}" != check && "${SECTION}" != all ]]; then
  echo '--section is only valid with --check' >&2
  exit 2
fi
if [[ "${ACTION}" != restart && -n "${HASH}" ]]; then
  echo '--expected-plan-hash is only valid with --apply-wave' >&2
  exit 2
fi
if [[ "${ACTION}" == restart ]]; then
  [[ "${ACK}" == "${ACK_RESTART}" && "${HASH}" =~ ^[a-f0-9]{64}$ ]] || {
    echo 'Apply denied: exact acknowledgement and fresh 64-character plan hash required' >&2
    exit 2
  }
elif [[ "${ACTION}" == migrate || "${ACTION}" == smoke ]]; then
  [[ "${ACK}" == "${ACK_MIGRATION}" ]] || {
    echo 'Apply denied: exact reviewed-migration acknowledgement required' >&2
    exit 2
  }
elif [[ -n "${ACK}" ]]; then
  echo '--acknowledge is only valid for apply operations' >&2; exit 2
fi
if [[ "${ACTION}" == restart || "${ACTION}" == migrate || "${ACTION}" == smoke ]]; then
  ((EUID == 0)) || { echo 'Apply denied: root required on TrueNAS' >&2; exit 2; }
  # The source checkout may be bind-mounted into running Apps. Refuse
  # mutation from detached review worktrees or unmerged PR branches.
  command -v git >/dev/null 2>&1 || { echo 'Apply denied: git required' >&2; exit 2; }
  CANONICAL_ROOT="$(cd -- "${NABLA_MIGRATION_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}" 2>/dev/null && pwd -P)" || {
    echo 'Apply denied: canonical TrueNAS checkout unavailable' >&2; exit 2;
  }
  [[ "${ROOT}" == "${CANONICAL_ROOT}" ]] || {
    echo 'Apply denied: only the canonical TrueNAS checkout can mutate Apps' >&2; exit 2;
  }
  CURRENT_BRANCH="$(git symbolic-ref -q --short HEAD 2>/dev/null || true)"
  [[ "${CURRENT_BRANCH}" == master ]] || {
    echo 'Apply denied: deploy only from reviewed master, never a Draft PR/worktree' >&2; exit 2;
  }
  if ! GIT_STATUS="$(git status --porcelain=v1 --ignore-submodules=all)"; then
    echo 'Apply denied: cannot verify canonical superproject cleanliness' >&2
    exit 2
  fi
  if [[ -n "${GIT_STATUS}" ]]; then
    echo 'Apply denied: canonical superproject is dirty; review/commit first' >&2
    exit 2
  fi
fi
[[ -x /usr/bin/env ]] || { echo 'POSIX environment unavailable' >&2; exit 2; }
[[ -f "${ROOT}/scripts/truenas/restart-catalog-v2-apps.py" ]] || {
  echo 'Wrong checkout: Catalog v2 planner not present' >&2; exit 2;
}
for command in python3 jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "Missing required TrueNAS command: ${command}" >&2; exit 2;
  }
done
# Guard against missing/symlinked extensions before any report or runtime action.
# shellcheck source=scripts/truenas/migration-diagnostic-sections.sh
READONLY_REGISTRY="${ROOT}/scripts/truenas/migration-diagnostic-sections.sh"
if [[ ! -f "${READONLY_REGISTRY}" || -L "${READONLY_REGISTRY}" ]]; then
  echo 'BLOCKED: read-only diagnostic registry missing or symlinked' >&2
  exit 2
fi
source "${READONLY_REGISTRY}"
if [[ -L "${REPORT_ROOT}" || ! "${REPORT_ROOT}" = /* ]]; then
  echo 'Unsafe report root (must be absolute directory, not symlink)' >&2; exit 2
fi
mkdir -p -- "${REPORT_ROOT}"
chmod -- 0700 "${REPORT_ROOT}"
[[ -d "${REPORT_ROOT}" && ! -L "${REPORT_ROOT}" ]] || exit 2
SESSION_DIR="$(mktemp -d "${REPORT_ROOT}/session-XXXXXXXX")"
chmod 0700 "${SESSION_DIR}"
SUMMARY="${SESSION_DIR}/summary.tsv"
: >"${SUMMARY}"
chmod 0600 "${SUMMARY}"
if [[ "${VERBOSE}" == true ]]; then diag_info "Private evidence: ${SESSION_DIR}"; fi
printf 'phase\tresult\tlog\n' >"${SUMMARY}"

PASS=0
FAILED=0
SKIPPED=0
WARNINGS=0
safe_failure_hint() {
  # Classify without exposing credential values, environment or raw logs.
  # Categories are fixed constants, not untrusted log fragments.
  local log="$1"
  [[ -f "${log}" ]] || { printf '%s' 'missing report'; return; }
  if grep -Eqi 'permission denied|operation not permitted' "${log}"; then
    printf '%s' 'permissions'
  elif grep -Eqi 'connect.timeout|timed out|connection refused' "${log}"; then
    printf '%s' 'connectivity/timeout'
  elif grep -Eqi 'unhealthy|health.?check' "${log}"; then
    printf '%s' 'healthcheck'
  elif grep -Eqi 'env file.*not found|missing.*secret|materialization.*missing' "${log}"; then
    printf '%s' 'runtime secrets'
  elif grep -Eqi 'no such file|file not found|cannot stat' "${log}"; then
    printf '%s' 'missing file'
  else
    printf '%s' 'see private report'
  fi
}
record() {
  local name="$1" state="$2" logfile="$3"
  printf '%s\t%s\t%s\n' "${name}" "${state}" "${logfile}" >>"${SUMMARY}"
  case "${state}" in
    PASS) PASS=$((PASS+1)); diag_ok "${name}" ;;
    FAIL)
      FAILED=$((FAILED+1))
      diag_fail "${name} — $(safe_failure_hint "${logfile}")"
      ;;
    SKIP) SKIPPED=$((SKIPPED+1)); diag_info "${name} — not checked" ;;
    WARN) WARNINGS=$((WARNINGS+1)); diag_warn "${name} — review required" ;;
  esac
  if [[ "${VERBOSE}" == true && "${state}" != PASS ]]; then
    diag_info "evidence: ${logfile}"
  fi
}
run_check() {
  local name="$1"; shift
  local logfile="${SESSION_DIR}/${name}.log"
  if "$@" >"${logfile}" 2>&1; then
    record "${name}" PASS "${logfile}"
  else
    record "${name}" FAIL "${logfile}"
  fi
}
run_optional_tool() {
  local name="$1" tool="$2"; shift 2
  if ! command -v "${tool}" >/dev/null 2>&1; then
    record "${name}" SKIP "missing ${tool}; use an operator workstation"
  else
    run_check "${name}" "$@"
  fi
}
wave_args() {
  case "$1" in
    core) WAVE_ARGS=() ;;
    gatus) WAVE_ARGS=(--include-gatus) ;;
    deferred) WAVE_ARGS=(--include-deferred) ;;
  esac
}
plan_wave() {
  local wave="$1" report hash ready
  wave_args "${wave}"
  report="${SESSION_DIR}/catalog-${wave}.json"
  python3 scripts/truenas/restart-catalog-v2-apps.py --check \
    "${WAVE_ARGS[@]}" --output "${report}" >"${SESSION_DIR}/catalog-${wave}.log" 2>&1 || {
    record "catalog-${wave}" FAIL "${SESSION_DIR}/catalog-${wave}.log"
    return 1
  }
  [[ -f "${report}" ]] || { record "catalog-${wave}" FAIL "${SESSION_DIR}/catalog-${wave}.log"; return 1; }
  if ! jq -e --arg wave "${wave}" '
      .inventorySource == "live-midclt" and
      .runtimeSecretsSource == "live-filesystem" and
      .selectedWave == $wave and
      (.planHash | type=="string" and test("^[a-f0-9]{64}$"))
    ' "${report}" >/dev/null; then
    record "catalog-${wave}" FAIL "${SESSION_DIR}/catalog-${wave}.log"
    return 1
  fi
  hash="$(jq -r .planHash "${report}")"
  ready="$(jq -r .selectedWaveReady "${report}")"
  if [[ "${ready}" == true ]]; then
    record "catalog-${wave}" PASS "${report}"
    # Opaque plan hash is safe to publish; raw plan remains private.
    # Required for exact plan acknowledgement. No credential or app config data.
    printf 'catalog_wave=%s plan_hash=%s selectedWaveReady=true\n' "${wave}" "${hash}"
  else
    record "catalog-${wave}" FAIL "${report}"
    diag_warn "catalog ${wave}: $(jq -r '.selectedWaveBlocker // "unknown"' "${report}")"
    printf 'catalog_wave=%s plan_hash=%s selectedWaveReady=false\n' "${wave}" "${hash}"
  fi
  printf '%s\n' "${hash}" >"${SESSION_DIR}/catalog-${wave}.sha256"
  [[ "${ready}" == true ]]
}

print_summary() {
  printf '\n'
  if (( FAILED > 0 )); then
    diag_fail "Read-only acceptance incomplete: ${FAILED} failing checks"
  elif (( WARNINGS > 0 || SKIPPED > 0 )); then
    diag_warn "Acceptance has unverified/optional checks"
  else
    diag_ok "All selected checks passed"
  fi
  printf 'Results: PASS=%d FAIL=%d WARN=%d SKIP=%d\n' "${PASS}" "${FAILED}" "${WARNINGS}" "${SKIPPED}"
  printf 'Private evidence: %s\n' "${SESSION_DIR}"
  printf 'Review: sudo cat %q\n' "${SUMMARY}"
}
if [[ "${ACTION}" == check ]]; then
  if [[ "${SECTION}" == all ]]; then
    for part in platform migrations catalog services ai sentry observability secrets convergence lan talos; do
      diag_section "" "${part}"
      check_section "${part}"
    done
  else
    check_section "${SECTION}"
  fi
  print_summary
  ((FAILED==0)) || exit 1
  exit 0
fi

if [[ "${ACTION}" == plan ]]; then
  plan_wave "${WAVE}" || { print_summary; exit 1; }
  print_summary
  exit 0
fi

if [[ "${ACTION}" == restart ]]; then
  # Double-check against live TrueNAS immediately before delegating. The
  # existing planner rechecks *again under its own mutation lock*.
  plan_wave "${WAVE}" || { print_summary; exit 1; }
  fresh="$(cat "${SESSION_DIR}/catalog-${WAVE}.sha256")"
  [[ "${fresh}" == "${HASH}" ]] || {
    echo 'BLOCKED: plan drift. Rerun --plan-wave and review the new plan.' >&2
    exit 1
  }
  wave_args "${WAVE}"
  if python3 scripts/truenas/restart-catalog-v2-apps.py --apply \
       "${WAVE_ARGS[@]}" --expected-plan-hash "${HASH}" \
       --acknowledge-downtime "${ACK_RESTART}" >"${SESSION_DIR}/apply-${WAVE}.log" 2>&1; then
    record "apply-${WAVE}" PASS "${SESSION_DIR}/apply-${WAVE}.log"
  else
    record "apply-${WAVE}" FAIL "${SESSION_DIR}/apply-${WAVE}.log"
  fi
  check_section services
  print_summary
  ((FAILED==0)) || exit 1
  exit 0
fi

if [[ "${ACTION}" == migrate ]]; then
  case "${STEP}" in
    sentry-system) SCRIPT="scripts/truenas/reconcile-sentry-system-secret.sh" ;;
    sentry-migrator) SCRIPT="scripts/truenas/reconcile-sentry-migrator-credential.sh" ;;
    gatus-config) SCRIPT="scripts/truenas/deploy-gatus.sh" ;;
  esac
  if bash "${SCRIPT}" --check >"${SESSION_DIR}/before-${STEP}.log" 2>&1; then
    record "before-${STEP}" PASS "${SESSION_DIR}/before-${STEP}.log"
  else
    if [[ "${ALLOW_DRIFT}" != true ]]; then
      record "before-${STEP}" FAIL "${SESSION_DIR}/before-${STEP}.log"
      echo 'BLOCKED: check failed. Inspect the log, then re-run with --allow-reviewed-drift if the repair is explicitly approved.' >&2
      print_summary
      exit 1
    fi
    record "before-${STEP}" WARN "${SESSION_DIR}/before-${STEP}.log"
  fi
  if bash "${SCRIPT}" --apply >"${SESSION_DIR}/apply-${STEP}.log" 2>&1; then
    record "apply-${STEP}" PASS "${SESSION_DIR}/apply-${STEP}.log"
  else
    record "apply-${STEP}" FAIL "${SESSION_DIR}/apply-${STEP}.log"
  fi
  run_check "after-${STEP}" bash "${SCRIPT}" --check
  print_summary
  ((FAILED==0)) || exit 1
  exit 0
fi

if [[ "${ACTION}" == smoke ]]; then
  command -v kubectl >/dev/null 2>&1 || {
    echo 'BLOCKED: kubectl required; execute CSI smoke from a configured operator host.' >&2
    exit 2
  }
  if bash scripts/talos/smoke-truenas-csi-nfs.sh --check >"${SESSION_DIR}/before-csi.log" 2>&1; then
    record before-csi PASS "${SESSION_DIR}/before-csi.log"
  else
    record before-csi FAIL "${SESSION_DIR}/before-csi.log"
    print_summary; exit 1
  fi
  if bash scripts/talos/smoke-truenas-csi-nfs.sh --apply >"${SESSION_DIR}/apply-csi.log" 2>&1; then
    record apply-csi PASS "${SESSION_DIR}/apply-csi.log"
  else
    record apply-csi FAIL "${SESSION_DIR}/apply-csi.log"
  fi
  print_summary
  ((FAILED==0)) || exit 1
fi
