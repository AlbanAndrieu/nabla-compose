#!/usr/bin/env bash
# Temporary operator wrapper for the 2026-10-24 TrueNAS migration acceptance.
# Default: read-only diagnostics. NEVER reboots TrueNAS or mutates Apps implicitly.
set -euo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${ROOT}"
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

  sudo bash scripts/truenas/finish-migrations-20261024.sh --check [--section all|platform|migrations|catalog|services|ai|talos]
  sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave core|gatus|deferred
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-wave core|gatus|deferred \
    --expected-plan-hash <64-hex-from-plan> \
    --acknowledge I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-step \
    sentry-system|sentry-migrator|openrag-secret|gatus-config \
    --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
  sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-csi-smoke \
    --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION

All modes write PRIVATE metadata/diagnostic logs under
/mnt/cpool/var/nabla/migration-20261024. Inspect the private logs before
proceeding. --check and --plan-wave never stop/start/redeploy Apps.
--apply-step runs its matching --check first; if drift makes the check fail,
review its report and repeat with --allow-reviewed-drift (explicit override).
No automatic remediation for DefectDojo, Docling, Hermes, OpenRAG ingestion,
Vaultwarden secret import or TrueNAS host reboot: see the runbook.
EOF
}

while (($#)); do
  case "$1" in
    --check) ACTION="check"; shift ;;
    --section) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; SECTION="$2"; shift 2 ;;
    --plan-wave) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="plan"; WAVE="$2"; shift 2 ;;
    --apply-wave) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="restart"; WAVE="$2"; shift 2 ;;
    --apply-step) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; ACTION="migrate"; STEP="$2"; shift 2 ;;
    --apply-csi-smoke) ACTION="smoke"; shift ;;
    --expected-plan-hash) [[ $# -ge 2 ]] || exit 2; HASH="$2"; shift 2 ;;
    --acknowledge) [[ $# -ge 2 ]] || exit 2; ACK="$2"; shift 2 ;;
    --allow-reviewed-drift) ALLOW_DRIFT=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument (see --help): %s\n' "$1" >&2; exit 2 ;;
  esac
done

case "${ACTION}" in check|plan|restart|migrate|smoke) ;; *) exit 2 ;; esac
case "${SECTION}" in all|platform|migrations|catalog|services|ai|talos) ;; *) echo 'Invalid section' >&2; exit 2 ;; esac
if [[ "${ACTION}" == plan || "${ACTION}" == restart ]]; then
  case "${WAVE}" in core|gatus|deferred) ;; *) echo 'Invalid wave' >&2; exit 2 ;; esac
fi
if [[ "${ACTION}" == migrate ]]; then
  case "${STEP}" in sentry-system|sentry-migrator|openrag-secret|gatus-config) ;; *) echo 'Invalid migration step' >&2; exit 2 ;; esac
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
echo "Private report directory: ${SESSION_DIR}"
printf 'phase\tresult\tlog\n' >"${SUMMARY}"

PASS=0
FAILED=0
SKIPPED=0
WARNINGS=0
record() {
  local name="$1" state="$2" logfile="$3"
  printf '%s\t%s\t%s\n' "${name}" "${state}" "${logfile}" >>"${SUMMARY}"
  case "${state}" in
    PASS) PASS=$((PASS+1)); printf '✅ %s\n' "${name}" ;;
    FAIL) FAILED=$((FAILED+1)); printf '❌ %s (private log: %s)\n' "${name}" "${logfile}" >&2 ;;
    SKIP) SKIPPED=$((SKIPPED+1)); printf '⚠️  %s skipped\n' "${name}" ;;
    WARN) WARNINGS=$((WARNINGS+1)); printf '⚠️  %s has operator-reviewed drift (private log: %s)\n' "${name}" "${logfile}" ;;
  esac
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
    printf '   selectedWaveReady=true; --expected-plan-hash %s\n' "${hash}"
  else
    record "catalog-${wave}" FAIL "${report}"
    printf '   selectedWaveBlocker: %s\n' "$(jq -r '.selectedWaveBlocker // "unknown"' "${report}")" >&2
  fi
  printf '%s\n' "${hash}" >"${SESSION_DIR}/catalog-${wave}.sha256"
  [[ "${ready}" == true ]]
}

check_section() {
  case "$1" in
    platform)
      run_check platform-health bash scripts/truenas/check-homelab-services.sh
      run_check docker-orphan-shims bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
      run_check pihole-dns-sync bash scripts/truenas/verify-pihole-dns-sync.sh
      run_check shared-data bash scripts/truenas/diagnose-shared-data-services.sh
      ;;
    migrations)
      run_check supported-runtime-audit python3 scripts/quality/audit-supported-runtimes.py --strict-eol
      run_check live-language-patches python3 scripts/truenas/audit-live-language-runtimes.py --check
      run_check migration-manifest python3 scripts/security/check-migration-readiness.py --check
      run_check secrets-runtime bash scripts/truenas/bootstrap-repository-runtime.sh --check
      run_check sentry-system-secret bash scripts/truenas/reconcile-sentry-system-secret.sh --check
      run_check sentry-migrator-secret bash scripts/truenas/reconcile-sentry-migrator-credential.sh --check
      run_check openrag-opensearch-secret bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
      run_check defectdojo-preflight bash scripts/truenas/preflight-defectdojo.sh
      run_check openwebui-pra bash scripts/truenas/diagnose-openwebui-backup-pra.sh --check
      ;;
    catalog)
      plan_wave core || true
      plan_wave gatus || true
      plan_wave deferred || true
      ;;
    services)
      run_check gatus bash scripts/truenas/diagnose-gatus.sh
      run_check sentry bash scripts/truenas/diagnose-sentry.sh --check
      run_check defectdojo bash scripts/truenas/diagnose-defectdojo.sh --check
      run_check cyberbro bash scripts/truenas/diagnose-cyberbro.sh
      run_check prometheus bash scripts/truenas/diagnose-prometheus-targets.sh --check
      run_check app-states bash scripts/truenas/triage-post-reboot-apps.sh
      ;;
    ai)
      run_check hermes-native bash scripts/truenas/diagnose-hermes-agent.sh --check
      # Required runtime secrets and actual failed Apps are blocking.
      run_check ai-runtime-recovery python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
      # Anthropic and OpenAI are opt-in cloud upstreams, not prerequisites
      # for the existing local LiteLLM service. Report lack as WARN only.
      if python3 scripts/truenas/check-litellm-hermes-credentials.py --check >"${SESSION_DIR}/litellm-provider-keys.log" 2>&1; then
        record litellm-provider-keys PASS "${SESSION_DIR}/litellm-provider-keys.log"
      else
        record litellm-provider-keys WARN "${SESSION_DIR}/litellm-provider-keys.log"
      fi
      ;;
    talos)
      if command -v kubectl >/dev/null 2>&1 && command -v talosctl >/dev/null 2>&1; then
        run_check talos-cluster bash scripts/talos/validate-cluster.sh
        run_check talos-supported-upgrade python3 scripts/talos/preflight-supported-upgrade.py --check
        run_check truenas-csi bash scripts/talos/smoke-truenas-csi-nfs.sh --check
      else
        record talos-cluster SKIP "kubectl/talosctl unavailable on TrueNAS; use an authorized workstation"
        record truenas-csi SKIP "kubectl/talosctl unavailable on TrueNAS; use an authorized workstation"
      fi
      ;;
  esac
}
print_summary() {
  printf '\nResult: PASS=%d FAIL=%d WARN=%d SKIP=%d; private logs=%s\n' "${PASS}" "${FAILED}" "${WARNINGS}" "${SKIPPED}" "${SESSION_DIR}"
  printf 'Review: sudo cat %q\n' "${SUMMARY}"
}
if [[ "${ACTION}" == check ]]; then
  if [[ "${SECTION}" == all ]]; then
    for part in platform migrations catalog services ai talos; do
      printf '\n-- %s --\n' "${part}"
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
    openrag-secret) SCRIPT="scripts/truenas/reconcile-openrag-opensearch-secret.sh" ;;
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
