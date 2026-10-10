#!/usr/bin/env bash
set -euo pipefail

# Repository-specific agent-first gate.
# Keep scripts/quality-gate.sh canonical across Nabla repositories; this wrapper
# adds cheap repo-specific checks learned from recent PR failures.

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

DEV_VENV="${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"
if [[ -d "${DEV_VENV}/bin" ]]; then
  # Always put the TrueNAS operator venv first. `mise run` may prepend its
  # project Python ahead of an already-present venv path.
  export PATH="${DEV_VENV}/bin:${PATH}"
fi

MODE="check"
PUBLISH=false
LOCAL_LOOP=false
TARGETED_ONLY=false
TARGETED_LABEL=""
case "${1:-}" in
  --fix)
    MODE="fix"
    shift
    ;;
  --preflight)
    MODE="preflight"
    shift
    ;;
  --loop)
    MODE="fix"
    LOCAL_LOOP=true
    TARGETED_ONLY=true
    TARGETED_LABEL="Local loop"
    shift
    ;;
  --ci)
    MODE="ci"
    TARGETED_ONLY=true
    TARGETED_LABEL="CI fast"
    shift
    ;;
  --publish)
    PUBLISH=true
    shift
    ;;
  -h|--help)
    cat <<'EOF'
Usage:
  bash scripts/agent-quality-gate.sh [--fix|--loop|--preflight|--ci|--publish]

Modes:
  default      strict local validation gate
  --fix        regenerate/fix deterministic artifacts, then run the full local gate
  --loop       regenerate/fix and run changed-file contracts only; use during edit iterations
  --preflight  Git-only safety gate before dependency installation/build work
  --ci         check-only changed-file gate; skips the full unit suite already required locally before push
  --publish    strict local gate plus canonical clean-tree publication check

Environment:
  QUALITY_BASE_REF                 override comparison base
  QUALITY_LOG_TAIL                 failure log lines to print (default: 32)
  QUALITY_LOG_LINE_MAX             maximum characters per emitted failure line (default: 320)
  QUALITY_SUMMARY_LINES            maximum failure-summary lines (default: 12)
  QUALITY_FIX_MAX_PASSES           deterministic fix passes (default: 6)
  NABLA_TRUENAS_DEV_VENV           preferred local dev venv (default: ~/.cache/nabla-compose/dev-venv)
  QUALITY_ALLOW_LARGE_DELETION=1   acknowledge an intentional large file truncation
EOF
    exit 0
    ;;
  "")
    ;;
  *)
    printf '❌ unknown argument: %s\n' "$1" >&2
    exit 2
    ;;
esac

if (($# > 0)); then
  printf '❌ unexpected argument: %s\n' "$1" >&2
  exit 2
fi

LOG_TAIL="${QUALITY_LOG_TAIL:-12}"
LOG_LINE_MAX="${QUALITY_LOG_LINE_MAX:-320}"
FIX_MAX_PASSES="${QUALITY_FIX_MAX_PASSES:-6}"
REVIEWED_LARGE_DELETIONS="${ROOT}/config/quality/reviewed-large-deletions.tsv"
if ! [[ "${LOG_TAIL}" =~ ^[1-9][0-9]*$ ]]; then
  printf '❌ QUALITY_LOG_TAIL must be a positive integer\n' >&2
  exit 2
fi
if ! [[ "${LOG_LINE_MAX}" =~ ^[1-9][0-9]*$ ]] || ((LOG_LINE_MAX < 120)); then
  printf '❌ QUALITY_LOG_LINE_MAX must be an integer >= 120\n' >&2
  exit 2
fi
if ! [[ "${FIX_MAX_PASSES}" =~ ^[1-9][0-9]*$ ]] || ((FIX_MAX_PASSES > 10)); then
  printf '❌ QUALITY_FIX_MAX_PASSES must be an integer between 1 and 10\n' >&2
  exit 2
fi

resolve_base_ref() {
  if [[ -n "${QUALITY_BASE_REF:-}" ]]; then
    printf '%s\n' "${QUALITY_BASE_REF}"
  elif git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
    git symbolic-ref --quiet --short refs/remotes/origin/HEAD
  elif git rev-parse --verify origin/main >/dev/null 2>&1; then
    printf '%s\n' "origin/main"
  elif git rev-parse --verify origin/master >/dev/null 2>&1; then
    printf '%s\n' "origin/master"
  elif git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    printf '%s\n' "HEAD~1"
  else
    printf '%s\n' "HEAD"
  fi
}

BASE_REF="$(resolve_base_ref)"

if [[ -x "${DEV_VENV}/bin/python" ]]; then
  PYTHON_CMD=("${DEV_VENV}/bin/python")
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=(python)
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=(python3)
else
  PYTHON_CMD=()
fi
CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "${CURRENT_BRANCH}" == "master" ]]; then
  printf '❌ QG_PROTECTED_BRANCH: agent workflow must not run/publish directly on master; use a dedicated branch and pull request\n' >&2
  exit 1
fi

print_bounded_log_lines() {
  awk -v max="${LOG_LINE_MAX}" '
    {
      if (length($0) > max) {
        printf "%s … [line truncated, %d chars omitted]\n", substr($0, 1, max), length($0) - max
      } else {
        print
      }
    }
  '
}

print_compact_log() {
  local log="$1"
  local summary=""

  # Summarize only failure IDs/statuses, not verbose pytest assertion
  # dumps, file diffs, successful hooks, or source code containing ERROR.
  # Full untruncated evidence remains in a private on-disk log.
  summary="$(grep -E '^(- hook id: |FAILED tests/|ERROR tests/|FAIL: |ERROR: |.*[.]{3,}Failed$|[0-9]+ failed|[0-9]+ error|=+ (FAILURES|ERRORS) =+|❌ QG_|\[ERROR\])' "${log}" || true)"
  shellcheck_summary="$(grep -E '^(In .* line [0-9]+:|.*SC[0-9]{4}.*)' "${log}" || true)"
  if [[ -n "${shellcheck_summary}" ]]; then
    summary="${summary}${summary:+
    local summary_limit="${QUALITY_SUMMARY_LINES:-10}"
    local summary_count
    [[ "${summary_limit}" =~ ^[1-9][0-9]*$ ]] || summary_limit=12
    summary_count="$(printf '%s\n' "${summary}" | wc -l)"
    printf '%s\n' '--- failure summary ---' >&2
    printf '%s\n' "${summary}" | awk -v max="${summary_limit}" 'NR <= max' |
      print_bounded_log_lines >&2
    if ((summary_count > summary_limit)); then
      printf '... %d additional summary lines omitted; inspect full local log if needed\n' \
        "$((summary_count - summary_limit))" >&2
    fi
  fi
  printf 'Full failure log: %s (private, mode 0600)\n' "${log}" >&2
  if [[ -z "${summary}" ]]; then
    printf '%s\n' "--- last ${LOG_TAIL} log lines (no recognizable summary) ---" >&2
    tail -n "${LOG_TAIL}" "${log}" | print_bounded_log_lines >&2 || true
  fi
}

run_compact() {
  local label="$1"
  shift
  local log
  local rc
  log="$(mktemp)"
  if "$@" >"${log}" 2>&1; then
    rm -f "${log}"
    printf '✅ %s\n' "${label}"
    return 0
  else
    rc=$?
  fi
  printf '❌ %s\n' "${label}" >&2
  print_compact_log "${log}"
  return "${rc}"
}

collect_changed_files() {
  {
    if [[ "${LOCAL_LOOP}" != true && "${BASE_REF}" != "HEAD" ]] &&
      git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=ACMR
    git diff --cached --name-only --diff-filter=ACMR
    git ls-files --others --exclude-standard
  } |
    awk 'NF' |
    sort -u |
    while IFS= read -r file; do
      if [[ -f "${file}" ]]; then
        printf '%s\n' "${file}"
      fi
    done
}

collect_deleted_files() {
  {
    if [[ "${LOCAL_LOOP}" != true && "${BASE_REF}" != "HEAD" ]] &&
      git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=D "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=D
    git diff --cached --name-only --diff-filter=D
  } |
    awk 'NF' |
    sort -u
}

# Process substitution masks Git errors; fail closed rather than skip tests.
if ! changed_output="$(collect_changed_files)" ||
  ! deleted_output="$(collect_deleted_files)"; then
  printf '❌ QG_GIT_SCOPE: failed to collect changed/deleted paths; no checks were skipped\n' >&2
  exit 2
fi
CHANGED_FILES=()
DELETED_FILES=()
[[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
[[ -z "${deleted_output}" ]] || mapfile -t DELETED_FILES <<<"${deleted_output}"

check_base_freshness() {
  if [[ "${BASE_REF}" == "HEAD" ]]; then
    return 0
  fi
  if ! git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
    printf '❌ QG_BASE_MISSING: comparison base %s is unavailable\n' "${BASE_REF}" >&2
    exit 1
  fi
  if ! git merge-base --is-ancestor "${BASE_REF}" HEAD; then
    printf '❌ QG_BASE_STALE: HEAD does not contain %s; update/rebase before publishing\n' "${BASE_REF}" >&2
    exit 1
  fi
  printf '✅ branch contains comparison base %s\n' "${BASE_REF}"
}

is_reviewed_large_deletion() {
  local file="$1"
  local current_state="${2:-PRESENT}"
  local base_blob current_blob

  [[ -f "${REVIEWED_LARGE_DELETIONS}" ]] || return 1
  base_blob="$(git rev-parse "${BASE_REF}:${file}" 2>/dev/null || true)"
  [[ -n "${base_blob}" ]] || return 1

  if [[ "${current_state}" == "DELETED" ]]; then
    current_blob="DELETED"
  else
    [[ -f "${file}" ]] || return 1
    current_blob="$(git hash-object "${file}")"
  fi

  awk -F '\t' \
    -v path="${file}" \
    -v base="${base_blob}" \
    -v current="${current_blob}" '
      $0 !~ /^#/ && $1 == path && $2 == base && $3 == current { found = 1 }
      END { exit(found ? 0 : 1) }
    ' "${REVIEWED_LARGE_DELETIONS}"
}

check_destructive_diff() {
  local large_deletion_failed=0
  if [[ "${QUALITY_ALLOW_LARGE_DELETION:-0}" == "1" || "${BASE_REF}" == "HEAD" ]]; then
    printf '✅ destructive-diff guard\n'
    return 0
  fi

  for file in "${CHANGED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|apps/homarr/generated/apps.json|apps/autokuma/static/generated-monitors.json|apps/gatus/config/config.yml|package-lock.json)
        continue
        ;;
      *.md|*.py|*.sh|*.yml|*.yaml|*.json|*.toml|*.hcl|*.tofu|Dockerfile*|Makefile)
        ;;
      *)
        continue
        ;;
    esac

    git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
    base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
    current_lines="$(wc -l <"${file}" | tr -d ' ')"
    if ((base_lines < 200 || current_lines >= base_lines)); then
      continue
    fi
    deleted_lines=$((base_lines - current_lines))
    deleted_percent=$((deleted_lines * 100 / base_lines))
    if ((deleted_lines >= 100 && deleted_percent >= 40)); then
      if is_reviewed_large_deletion "${file}" PRESENT; then
        printf '✅ reviewed large deletion: %s lost %d/%d lines (%d%%) with exact blob approval\n' \
          "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}"
        continue
      fi
      printf '❌ QG_LARGE_DELETION: %s lost %d/%d lines (%d%%); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
        "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}" >&2
      large_deletion_failed=1
    fi
  done

  for file in "${DELETED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|apps/homarr/generated/apps.json|apps/autokuma/static/generated-monitors.json|apps/gatus/config/config.yml|package-lock.json)
        continue
        ;;
      *.md|*.py|*.sh|*.yml|*.yaml|*.json|*.toml|*.hcl|*.tofu|Dockerfile*|Makefile)
        ;;
      *)
        continue
        ;;
    esac

    git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
    base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
    if ((base_lines >= 200)); then
      if is_reviewed_large_deletion "${file}" DELETED; then
        printf '✅ reviewed large deletion: %s deleted (%d lines) with exact blob approval\n' \
          "${file}" "${base_lines}"
        continue
      fi
      printf '❌ QG_LARGE_DELETION: %s was deleted (%d lines); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
        "${file}" "${base_lines}" >&2
      large_deletion_failed=1
    fi
  done

  if ((large_deletion_failed != 0)); then
    exit 1
  fi
  printf '✅ destructive-diff guard\n'
}

check_exec_bits() {
  local exec_bit_failed=0
  local file first_line mode meta path current_mode

  # Git 100755 means the checked-out script must be executable by user/group/other.
  # On TrueNAS, chmod +x on a 0600 file yields 0700, which breaks stat-based
  # lifecycle contracts even though Git still records the correct executable bit.
  while IFS=$'\t' read -r meta path; do
    mode="${meta%% *}"
    [[ "${mode}" == "100755" ]] || continue
    [[ -f "${path}" ]] || continue
    current_mode="$(stat -c '%a' -- "${path}" 2>/dev/null || true)"
    if [[ "${current_mode}" != "755" ]]; then
      chmod 755 -- "${path}"
      printf '🛠️  working-tree mode restored from Git index: %s %s->755\n' \
        "${path}" "${current_mode:-unknown}"
    fi
  done < <(git ls-files --stage)

  for file in "${CHANGED_FILES[@]}"; do
    [[ -f "${file}" ]] || continue
    IFS= read -r first_line <"${file}" || true
    [[ "${first_line:-}" == '#!'* ]] || continue

    if git ls-files --error-unmatch -- "${file}" >/dev/null 2>&1; then
      mode="$(git ls-files --stage -- "${file}" | awk 'NR == 1 {print $1}')"
      if [[ "${mode}" != "100755" ]]; then
        if [[ "${MODE}" == "fix" ]]; then
          git add --chmod=+x -- "${file}"
          chmod 755 -- "${file}"
          printf '🛠️  executable bit restored for %s\n' "${file}"
        else
          printf '❌ QG_EXEC_BIT: %s has a shebang but Git mode is %s; run git add --chmod=+x %q\n' \
            "${file}" "${mode:-unknown}" "${file}" >&2
          exec_bit_failed=1
        fi
      fi
    elif [[ ! -x "${file}" ]]; then
      if [[ "${MODE}" == "fix" ]]; then
        chmod 755 -- "${file}"
        printf '🛠️  executable bit restored for untracked %s\n' "${file}"
      else
        printf '❌ QG_EXEC_BIT: untracked %s has a shebang but is not executable\n' "${file}" >&2
        exec_bit_failed=1
      fi
    fi
  done

  if ((exec_bit_failed != 0)); then
    exit 1
  fi
  printf '✅ executable-script contract\n'
}

check_base_freshness
check_destructive_diff
check_exec_bits

if [[ "${MODE}" == "preflight" ]]; then
  printf '✅ Git-only agent preflight passed before dependency installation/build work\n'
  exit 0
fi

(("${#PYTHON_CMD[@]}" > 0)) || {
  echo "❌ QG_PYTHON_MISSING: python or python3 is required" >&2
  echo "   Run: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
  exit 1
}

if ! "${PYTHON_CMD[@]}" -c 'import pytest, yaml' >/dev/null 2>&1; then
  echo "❌ QG_PYTHON_DEPS_MISSING: pytest and PyYAML are required by local contract hooks" >&2
  echo "   TrueNAS: bash scripts/truenas/bootstrap-dev-tools.sh --persist-shell-path && source ~/.bashrc" >&2
  echo "   Verify: ~/.cache/nabla-compose/dev-venv/bin/python -c 'import pytest, yaml'" >&2
  exit 1
fi

agent_gate_changed=false
for file in "${CHANGED_FILES[@]}"; do
  if [[ "${file}" == "scripts/agent-quality-gate.sh" ]]; then
    agent_gate_changed=true
    break
  fi
done

if [[ "${MODE}" != "fix" && "${agent_gate_changed}" == true ]]; then
  command -v pre-commit >/dev/null 2>&1 || {
    echo "❌ pre-commit is required; run 'mise run hooks' first" >&2
    echo "   TrueNAS without mise: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
    exit 1
  }
  run_compact "agent gate shell formatting" \
    pre-commit run shfmt --files scripts/agent-quality-gate.sh
  run_compact "agent gate shell lint" \
    pre-commit run shellcheck --files scripts/agent-quality-gate.sh
  run_compact "agent gate shell style" \
    pre-commit run bashate --files scripts/agent-quality-gate.sh
fi

worktree_fingerprint() {
  {
    git status --porcelain=v1
    for file in "${CHANGED_FILES[@]}"; do
      [[ -f "${file}" ]] || continue
      printf '%s %s\n' "$(git hash-object -- "${file}")" "${file}"
    done
  } | git hash-object --stdin
}

if [[ "${MODE}" == "fix" ]]; then
  command -v pre-commit >/dev/null 2>&1 || {
    echo "❌ pre-commit is required; run 'mise run hooks' first" >&2
    echo "   TrueNAS without mise: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
    exit 1
  }

  generator_scope_changed=false
  for file in "${CHANGED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|catalog/service-topology.static.json|catalog/service-icons.json|catalog/service-consumers.static.yml|scripts/generate-service-topology.py|scripts/generate-service-consumers.py|scripts/nabla_ops/compose_paths.py|apps/*.yml|apps/*.yaml|compose*.yml|compose*.yaml|docker-compose*.yml|docker-compose*.yaml)
        generator_scope_changed=true
        break
        ;;
    esac
  done

  for ((pass = 1; pass <= FIX_MAX_PASSES; pass++)); do
    printf '🔁 deterministic fix pass %d/%d\n' "${pass}" "${FIX_MAX_PASSES}"
    if [[ "${generator_scope_changed}" == true ]]; then
      run_compact "regenerate declared service topology" \
        "${PYTHON_CMD[@]}" scripts/generate-service-topology.py
      run_compact "regenerate service consumers" \
        "${PYTHON_CMD[@]}" scripts/generate-service-consumers.py
    fi

    if ! changed_output="$(collect_changed_files)"; then
      printf '❌ QG_GIT_SCOPE: failed to refresh changed paths during fix pass\\n' >&2
      exit 2
    fi
    CHANGED_FILES=()
    [[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
    if (("${#CHANGED_FILES[@]}" == 0)); then
      printf '✅ no changed files require formatter/linter fixes\n'
      exit 0
    fi

    before_fingerprint="$(worktree_fingerprint)"
    log="$(mktemp)"
    rc=0
    pre-commit run --hook-stage pre-commit \
      --files "${CHANGED_FILES[@]}" --show-diff-on-failure >"${log}" 2>&1 || rc=$?
    if ! changed_output="$(collect_changed_files)"; then
      printf '❌ QG_GIT_SCOPE: failed to refresh changed paths during fix pass\\n' >&2
      exit 2
    fi
    CHANGED_FILES=()
    [[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
    after_fingerprint="$(worktree_fingerprint)"

    if ((rc == 0)) && [[ "${after_fingerprint}" == "${before_fingerprint}" ]]; then
      rm -f "${log}"
      printf '✅ deterministic formatter/linter fixes converged in %d pass(es)\n' "${pass}"
      if [[ "${TARGETED_ONLY}" == true ]]; then
        printf 'ℹ️  continuing with %s changed-file contracts and canonical changed-file gate\n' "${TARGETED_LABEL}"
      else
        printf 'ℹ️  continuing with the full local unit/contract and canonical quality gates\n'
      fi
      break
    fi

    if [[ "${after_fingerprint}" != "${before_fingerprint}" ]]; then
      rm -f "${log}"
      if ((pass == FIX_MAX_PASSES)); then
        printf '❌ QG_FIX_NON_CONVERGENT: deterministic fixes did not converge after %d passes\n' "${FIX_MAX_PASSES}" >&2
        exit 1
      fi
      printf '🛠️  Pre-commit changed files; rerunning the changed-file gate\n'
      continue
    fi

    printf '❌ QG_FIX_STALLED: Pre-commit failed without changing files; fix the reported error instead of repeating identical passes\n' >&2
    print_compact_log "${log}"
    exit "${rc}"
  done
fi

edge_security_contract_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    apps/crowdsec/*|scripts/pfsense/diagnose-recover.sh|scripts/truenas/deploy-crowdsec.sh|scripts/truenas/diagnose-crowdsec-cutover.sh|scripts/lib/truenas.sh|tests/test_pfsense_diagnose_recover_contract.py|tests/test_crowdsec_cutover_contract.py|docs/pfsense-diagnose-recover.md|docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md)
      edge_security_contract_scope_changed=true
      break
      ;;
  esac
done

if [[ "${edge_security_contract_scope_changed}" == true ]]; then
  run_compact "pfSense/CrowdSec targeted contracts" \
    "${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1 \
    --tb=short --show-capture=no \
    tests/test_pfsense_diagnose_recover_contract.py \
    tests/test_crowdsec_cutover_contract.py \
    tests/test_truenas_deploy_output_contract.py
fi

if [[ "${LOCAL_LOOP}" == true ]]; then
  git diff --check
  git diff --cached --check
  printf '✅ Agent local loop passed: deterministic fixes and changed-file contracts converged; full suite deferred to pre-push.\n'
  exit 0
fi

runtime_primitive_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    config/quality/runtime-primitives.json|scripts/*.sh|tests/test_runtime_primitive_duplication.py)
      runtime_primitive_scope_changed=true
      break
      ;;
  esac
done

if [[ "${TARGETED_ONLY}" != true || "${runtime_primitive_scope_changed}" == true ]]; then
  run_compact "migrated runtime primitive ownership is unique" \
    "${PYTHON_CMD[@]}" scripts/quality/check-runtime-primitive-duplication.py
else
  printf 'ℹ️  %s mode: runtime primitive ownership check skipped because no shell primitive input changed\n' "${TARGETED_LABEL}"
fi

generated_contract_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    catalog/service-topology.json|catalog/services.json|catalog/service-topology.static.json|catalog/service-icons.json|scripts/generate-service-topology.py|scripts/generate-service-consumers.py|apps/*/compose.yml|apps/*/compose.yaml|apps/*.yml|apps/*.yaml|compose*.yml|compose*.yaml|docker-compose*.yml|docker-compose*.yaml)
      generated_contract_scope_changed=true
      break
      ;;
  esac
done

if [[ "${TARGETED_ONLY}" != true || "${generated_contract_scope_changed}" == true ]]; then
  run_compact "declared service topology is synchronized" \
    "${PYTHON_CMD[@]}" scripts/generate-service-topology.py --check
  run_compact "Homarr/Gatus/AutoKuma consumers are synchronized" \
    "${PYTHON_CMD[@]}" scripts/generate-service-consumers.py --check
else
  printf 'ℹ️  %s mode: generated topology/consumer checks skipped because no generator input changed\n' "${TARGETED_LABEL}"
fi

if [[ "${TARGETED_ONLY}" == true ]]; then
  printf 'ℹ️  %s mode: full repository unit/contract suite is deferred to the local pre-push publication gate\n' "${TARGETED_LABEL}"
else
  run_compact "repository unit/contract tests" \
    "${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1 \
    --tb=short --show-capture=no tests
fi

CANONICAL_SKIP="service-topology-sync,service-consumer-contract"
if [[ -n "${SKIP:-}" ]]; then
  CANONICAL_SKIP="${SKIP},${CANONICAL_SKIP}"
fi

if [[ "${PUBLISH}" == true ]]; then
  run_compact "canonical formatter/linter/security publication gate" \
    env SKIP="${CANONICAL_SKIP}" bash scripts/quality-gate.sh --publish
  echo "✅ Agent publication gate passed; repository is clean and safe to publish."
else
  run_compact "canonical formatter/linter/security gate" \
    env SKIP="${CANONICAL_SKIP}" bash scripts/quality-gate.sh
  echo "✅ Agent quality gate passed."
fi
\n'}${shellcheck_summary}"
  fi
  if [[ -n "${summary}" ]]; then
    local summary_limit="${QUALITY_SUMMARY_LINES:-10}"
    local summary_count
    [[ "${summary_limit}" =~ ^[1-9][0-9]*$ ]] || summary_limit=12
    summary_count="$(printf '%s\n' "${summary}" | wc -l)"
    printf '%s\n' '--- failure summary ---' >&2
    printf '%s\n' "${summary}" | awk -v max="${summary_limit}" 'NR <= max' |
      print_bounded_log_lines >&2
    if ((summary_count > summary_limit)); then
      printf '... %d additional summary lines omitted; inspect full local log if needed\n' \
        "$((summary_count - summary_limit))" >&2
    fi
  fi
  printf 'Full failure log: %s (private, mode 0600)\n' "${log}" >&2
  if [[ -z "${summary}" ]]; then
    printf '%s\n' "--- last ${LOG_TAIL} log lines (no recognizable summary) ---" >&2
    tail -n "${LOG_TAIL}" "${log}" | print_bounded_log_lines >&2 || true
  fi
}

run_compact() {
  local label="$1"
  shift
  local log
  local rc
  log="$(mktemp)"
  if "$@" >"${log}" 2>&1; then
    rm -f "${log}"
    printf '✅ %s\n' "${label}"
    return 0
  else
    rc=$?
  fi
  printf '❌ %s\n' "${label}" >&2
  print_compact_log "${log}"
  return "${rc}"
}

collect_changed_files() {
  {
    if [[ "${LOCAL_LOOP}" != true && "${BASE_REF}" != "HEAD" ]] &&
      git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=ACMR
    git diff --cached --name-only --diff-filter=ACMR
    git ls-files --others --exclude-standard
  } |
    awk 'NF' |
    sort -u |
    while IFS= read -r file; do
      if [[ -f "${file}" ]]; then
        printf '%s\n' "${file}"
      fi
    done
}

collect_deleted_files() {
  {
    if [[ "${LOCAL_LOOP}" != true && "${BASE_REF}" != "HEAD" ]] &&
      git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=D "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=D
    git diff --cached --name-only --diff-filter=D
  } |
    awk 'NF' |
    sort -u
}

# Process substitution masks Git errors; fail closed rather than skip tests.
if ! changed_output="$(collect_changed_files)" ||
  ! deleted_output="$(collect_deleted_files)"; then
  printf '❌ QG_GIT_SCOPE: failed to collect changed/deleted paths; no checks were skipped\n' >&2
  exit 2
fi
CHANGED_FILES=()
DELETED_FILES=()
[[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
[[ -z "${deleted_output}" ]] || mapfile -t DELETED_FILES <<<"${deleted_output}"

check_base_freshness() {
  if [[ "${BASE_REF}" == "HEAD" ]]; then
    return 0
  fi
  if ! git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
    printf '❌ QG_BASE_MISSING: comparison base %s is unavailable\n' "${BASE_REF}" >&2
    exit 1
  fi
  if ! git merge-base --is-ancestor "${BASE_REF}" HEAD; then
    printf '❌ QG_BASE_STALE: HEAD does not contain %s; update/rebase before publishing\n' "${BASE_REF}" >&2
    exit 1
  fi
  printf '✅ branch contains comparison base %s\n' "${BASE_REF}"
}

is_reviewed_large_deletion() {
  local file="$1"
  local current_state="${2:-PRESENT}"
  local base_blob current_blob

  [[ -f "${REVIEWED_LARGE_DELETIONS}" ]] || return 1
  base_blob="$(git rev-parse "${BASE_REF}:${file}" 2>/dev/null || true)"
  [[ -n "${base_blob}" ]] || return 1

  if [[ "${current_state}" == "DELETED" ]]; then
    current_blob="DELETED"
  else
    [[ -f "${file}" ]] || return 1
    current_blob="$(git hash-object "${file}")"
  fi

  awk -F '\t' \
    -v path="${file}" \
    -v base="${base_blob}" \
    -v current="${current_blob}" '
      $0 !~ /^#/ && $1 == path && $2 == base && $3 == current { found = 1 }
      END { exit(found ? 0 : 1) }
    ' "${REVIEWED_LARGE_DELETIONS}"
}

check_destructive_diff() {
  local large_deletion_failed=0
  if [[ "${QUALITY_ALLOW_LARGE_DELETION:-0}" == "1" || "${BASE_REF}" == "HEAD" ]]; then
    printf '✅ destructive-diff guard\n'
    return 0
  fi

  for file in "${CHANGED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|apps/homarr/generated/apps.json|apps/autokuma/static/generated-monitors.json|apps/gatus/config/config.yml|package-lock.json)
        continue
        ;;
      *.md|*.py|*.sh|*.yml|*.yaml|*.json|*.toml|*.hcl|*.tofu|Dockerfile*|Makefile)
        ;;
      *)
        continue
        ;;
    esac

    git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
    base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
    current_lines="$(wc -l <"${file}" | tr -d ' ')"
    if ((base_lines < 200 || current_lines >= base_lines)); then
      continue
    fi
    deleted_lines=$((base_lines - current_lines))
    deleted_percent=$((deleted_lines * 100 / base_lines))
    if ((deleted_lines >= 100 && deleted_percent >= 40)); then
      if is_reviewed_large_deletion "${file}" PRESENT; then
        printf '✅ reviewed large deletion: %s lost %d/%d lines (%d%%) with exact blob approval\n' \
          "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}"
        continue
      fi
      printf '❌ QG_LARGE_DELETION: %s lost %d/%d lines (%d%%); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
        "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}" >&2
      large_deletion_failed=1
    fi
  done

  for file in "${DELETED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|apps/homarr/generated/apps.json|apps/autokuma/static/generated-monitors.json|apps/gatus/config/config.yml|package-lock.json)
        continue
        ;;
      *.md|*.py|*.sh|*.yml|*.yaml|*.json|*.toml|*.hcl|*.tofu|Dockerfile*|Makefile)
        ;;
      *)
        continue
        ;;
    esac

    git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
    base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
    if ((base_lines >= 200)); then
      if is_reviewed_large_deletion "${file}" DELETED; then
        printf '✅ reviewed large deletion: %s deleted (%d lines) with exact blob approval\n' \
          "${file}" "${base_lines}"
        continue
      fi
      printf '❌ QG_LARGE_DELETION: %s was deleted (%d lines); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
        "${file}" "${base_lines}" >&2
      large_deletion_failed=1
    fi
  done

  if ((large_deletion_failed != 0)); then
    exit 1
  fi
  printf '✅ destructive-diff guard\n'
}

check_exec_bits() {
  local exec_bit_failed=0
  local file first_line mode meta path current_mode

  # Git 100755 means the checked-out script must be executable by user/group/other.
  # On TrueNAS, chmod +x on a 0600 file yields 0700, which breaks stat-based
  # lifecycle contracts even though Git still records the correct executable bit.
  while IFS=$'\t' read -r meta path; do
    mode="${meta%% *}"
    [[ "${mode}" == "100755" ]] || continue
    [[ -f "${path}" ]] || continue
    current_mode="$(stat -c '%a' -- "${path}" 2>/dev/null || true)"
    if [[ "${current_mode}" != "755" ]]; then
      chmod 755 -- "${path}"
      printf '🛠️  working-tree mode restored from Git index: %s %s->755\n' \
        "${path}" "${current_mode:-unknown}"
    fi
  done < <(git ls-files --stage)

  for file in "${CHANGED_FILES[@]}"; do
    [[ -f "${file}" ]] || continue
    IFS= read -r first_line <"${file}" || true
    [[ "${first_line:-}" == '#!'* ]] || continue

    if git ls-files --error-unmatch -- "${file}" >/dev/null 2>&1; then
      mode="$(git ls-files --stage -- "${file}" | awk 'NR == 1 {print $1}')"
      if [[ "${mode}" != "100755" ]]; then
        if [[ "${MODE}" == "fix" ]]; then
          git add --chmod=+x -- "${file}"
          chmod 755 -- "${file}"
          printf '🛠️  executable bit restored for %s\n' "${file}"
        else
          printf '❌ QG_EXEC_BIT: %s has a shebang but Git mode is %s; run git add --chmod=+x %q\n' \
            "${file}" "${mode:-unknown}" "${file}" >&2
          exec_bit_failed=1
        fi
      fi
    elif [[ ! -x "${file}" ]]; then
      if [[ "${MODE}" == "fix" ]]; then
        chmod 755 -- "${file}"
        printf '🛠️  executable bit restored for untracked %s\n' "${file}"
      else
        printf '❌ QG_EXEC_BIT: untracked %s has a shebang but is not executable\n' "${file}" >&2
        exec_bit_failed=1
      fi
    fi
  done

  if ((exec_bit_failed != 0)); then
    exit 1
  fi
  printf '✅ executable-script contract\n'
}

check_base_freshness
check_destructive_diff
check_exec_bits

if [[ "${MODE}" == "preflight" ]]; then
  printf '✅ Git-only agent preflight passed before dependency installation/build work\n'
  exit 0
fi

(("${#PYTHON_CMD[@]}" > 0)) || {
  echo "❌ QG_PYTHON_MISSING: python or python3 is required" >&2
  echo "   Run: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
  exit 1
}

if ! "${PYTHON_CMD[@]}" -c 'import pytest, yaml' >/dev/null 2>&1; then
  echo "❌ QG_PYTHON_DEPS_MISSING: pytest and PyYAML are required by local contract hooks" >&2
  echo "   TrueNAS: bash scripts/truenas/bootstrap-dev-tools.sh --persist-shell-path && source ~/.bashrc" >&2
  echo "   Verify: ~/.cache/nabla-compose/dev-venv/bin/python -c 'import pytest, yaml'" >&2
  exit 1
fi

agent_gate_changed=false
for file in "${CHANGED_FILES[@]}"; do
  if [[ "${file}" == "scripts/agent-quality-gate.sh" ]]; then
    agent_gate_changed=true
    break
  fi
done

if [[ "${MODE}" != "fix" && "${agent_gate_changed}" == true ]]; then
  command -v pre-commit >/dev/null 2>&1 || {
    echo "❌ pre-commit is required; run 'mise run hooks' first" >&2
    echo "   TrueNAS without mise: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
    exit 1
  }
  run_compact "agent gate shell formatting" \
    pre-commit run shfmt --files scripts/agent-quality-gate.sh
  run_compact "agent gate shell lint" \
    pre-commit run shellcheck --files scripts/agent-quality-gate.sh
  run_compact "agent gate shell style" \
    pre-commit run bashate --files scripts/agent-quality-gate.sh
fi

worktree_fingerprint() {
  {
    git status --porcelain=v1
    for file in "${CHANGED_FILES[@]}"; do
      [[ -f "${file}" ]] || continue
      printf '%s %s\n' "$(git hash-object -- "${file}")" "${file}"
    done
  } | git hash-object --stdin
}

if [[ "${MODE}" == "fix" ]]; then
  command -v pre-commit >/dev/null 2>&1 || {
    echo "❌ pre-commit is required; run 'mise run hooks' first" >&2
    echo "   TrueNAS without mise: bash scripts/truenas/bootstrap-dev-tools.sh" >&2
    exit 1
  }

  generator_scope_changed=false
  for file in "${CHANGED_FILES[@]}"; do
    case "${file}" in
      catalog/service-topology.json|catalog/services.json|catalog/service-topology.static.json|catalog/service-icons.json|catalog/service-consumers.static.yml|scripts/generate-service-topology.py|scripts/generate-service-consumers.py|scripts/nabla_ops/compose_paths.py|apps/*.yml|apps/*.yaml|compose*.yml|compose*.yaml|docker-compose*.yml|docker-compose*.yaml)
        generator_scope_changed=true
        break
        ;;
    esac
  done

  for ((pass = 1; pass <= FIX_MAX_PASSES; pass++)); do
    printf '🔁 deterministic fix pass %d/%d\n' "${pass}" "${FIX_MAX_PASSES}"
    if [[ "${generator_scope_changed}" == true ]]; then
      run_compact "regenerate declared service topology" \
        "${PYTHON_CMD[@]}" scripts/generate-service-topology.py
      run_compact "regenerate service consumers" \
        "${PYTHON_CMD[@]}" scripts/generate-service-consumers.py
    fi

    if ! changed_output="$(collect_changed_files)"; then
      printf '❌ QG_GIT_SCOPE: failed to refresh changed paths during fix pass\\n' >&2
      exit 2
    fi
    CHANGED_FILES=()
    [[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
    if (("${#CHANGED_FILES[@]}" == 0)); then
      printf '✅ no changed files require formatter/linter fixes\n'
      exit 0
    fi

    before_fingerprint="$(worktree_fingerprint)"
    log="$(mktemp)"
    rc=0
    pre-commit run --hook-stage pre-commit \
      --files "${CHANGED_FILES[@]}" --show-diff-on-failure >"${log}" 2>&1 || rc=$?
    if ! changed_output="$(collect_changed_files)"; then
      printf '❌ QG_GIT_SCOPE: failed to refresh changed paths during fix pass\\n' >&2
      exit 2
    fi
    CHANGED_FILES=()
    [[ -z "${changed_output}" ]] || mapfile -t CHANGED_FILES <<<"${changed_output}"
    after_fingerprint="$(worktree_fingerprint)"

    if ((rc == 0)) && [[ "${after_fingerprint}" == "${before_fingerprint}" ]]; then
      rm -f "${log}"
      printf '✅ deterministic formatter/linter fixes converged in %d pass(es)\n' "${pass}"
      if [[ "${TARGETED_ONLY}" == true ]]; then
        printf 'ℹ️  continuing with %s changed-file contracts and canonical changed-file gate\n' "${TARGETED_LABEL}"
      else
        printf 'ℹ️  continuing with the full local unit/contract and canonical quality gates\n'
      fi
      break
    fi

    if [[ "${after_fingerprint}" != "${before_fingerprint}" ]]; then
      rm -f "${log}"
      if ((pass == FIX_MAX_PASSES)); then
        printf '❌ QG_FIX_NON_CONVERGENT: deterministic fixes did not converge after %d passes\n' "${FIX_MAX_PASSES}" >&2
        exit 1
      fi
      printf '🛠️  Pre-commit changed files; rerunning the changed-file gate\n'
      continue
    fi

    printf '❌ QG_FIX_STALLED: Pre-commit failed without changing files; fix the reported error instead of repeating identical passes\n' >&2
    print_compact_log "${log}"
    exit "${rc}"
  done
fi

edge_security_contract_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    apps/crowdsec/*|scripts/pfsense/diagnose-recover.sh|scripts/truenas/deploy-crowdsec.sh|scripts/truenas/diagnose-crowdsec-cutover.sh|scripts/lib/truenas.sh|tests/test_pfsense_diagnose_recover_contract.py|tests/test_crowdsec_cutover_contract.py|docs/pfsense-diagnose-recover.md|docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md)
      edge_security_contract_scope_changed=true
      break
      ;;
  esac
done

if [[ "${edge_security_contract_scope_changed}" == true ]]; then
  run_compact "pfSense/CrowdSec targeted contracts" \
    "${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1 \
    --tb=short --show-capture=no \
    tests/test_pfsense_diagnose_recover_contract.py \
    tests/test_crowdsec_cutover_contract.py \
    tests/test_truenas_deploy_output_contract.py
fi

if [[ "${LOCAL_LOOP}" == true ]]; then
  git diff --check
  git diff --cached --check
  printf '✅ Agent local loop passed: deterministic fixes and changed-file contracts converged; full suite deferred to pre-push.\n'
  exit 0
fi

runtime_primitive_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    config/quality/runtime-primitives.json|scripts/*.sh|tests/test_runtime_primitive_duplication.py)
      runtime_primitive_scope_changed=true
      break
      ;;
  esac
done

if [[ "${TARGETED_ONLY}" != true || "${runtime_primitive_scope_changed}" == true ]]; then
  run_compact "migrated runtime primitive ownership is unique" \
    "${PYTHON_CMD[@]}" scripts/quality/check-runtime-primitive-duplication.py
else
  printf 'ℹ️  %s mode: runtime primitive ownership check skipped because no shell primitive input changed\n' "${TARGETED_LABEL}"
fi

generated_contract_scope_changed=false
for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    catalog/service-topology.json|catalog/services.json|catalog/service-topology.static.json|catalog/service-icons.json|scripts/generate-service-topology.py|scripts/generate-service-consumers.py|apps/*/compose.yml|apps/*/compose.yaml|apps/*.yml|apps/*.yaml|compose*.yml|compose*.yaml|docker-compose*.yml|docker-compose*.yaml)
      generated_contract_scope_changed=true
      break
      ;;
  esac
done

if [[ "${TARGETED_ONLY}" != true || "${generated_contract_scope_changed}" == true ]]; then
  run_compact "declared service topology is synchronized" \
    "${PYTHON_CMD[@]}" scripts/generate-service-topology.py --check
  run_compact "Homarr/Gatus/AutoKuma consumers are synchronized" \
    "${PYTHON_CMD[@]}" scripts/generate-service-consumers.py --check
else
  printf 'ℹ️  %s mode: generated topology/consumer checks skipped because no generator input changed\n' "${TARGETED_LABEL}"
fi

if [[ "${TARGETED_ONLY}" == true ]]; then
  printf 'ℹ️  %s mode: full repository unit/contract suite is deferred to the local pre-push publication gate\n' "${TARGETED_LABEL}"
else
  run_compact "repository unit/contract tests" \
    "${PYTHON_CMD[@]}" -m pytest -q --disable-warnings --maxfail=1 \
    --tb=short --show-capture=no tests
fi

CANONICAL_SKIP="service-topology-sync,service-consumer-contract"
if [[ -n "${SKIP:-}" ]]; then
  CANONICAL_SKIP="${SKIP},${CANONICAL_SKIP}"
fi

if [[ "${PUBLISH}" == true ]]; then
  run_compact "canonical formatter/linter/security publication gate" \
    env SKIP="${CANONICAL_SKIP}" bash scripts/quality-gate.sh --publish
  echo "✅ Agent publication gate passed; repository is clean and safe to publish."
else
  run_compact "canonical formatter/linter/security gate" \
    env SKIP="${CANONICAL_SKIP}" bash scripts/quality-gate.sh
  echo "✅ Agent quality gate passed."
fi
