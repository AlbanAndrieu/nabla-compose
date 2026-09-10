#!/usr/bin/env bash
set -euo pipefail

# Repository-specific agent-first gate.
# Keep scripts/quality-gate.sh canonical across Nabla repositories; this wrapper
# adds cheap repo-specific checks learned from recent PR failures.

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

MODE="check"
PUBLISH=false
case "${1:-}" in
  --fix)
    MODE="fix"
    shift
    ;;
  --preflight)
    MODE="preflight"
    shift
    ;;
  --publish)
    PUBLISH=true
    shift
    ;;
  -h|--help)
    cat <<'EOF'
Usage:
  bash scripts/agent-quality-gate.sh [--fix|--preflight|--publish]

Modes:
  default      strict validation gate
  --fix        regenerate deterministic artifacts and converge pre-commit fixes
  --preflight  Git-only safety gate before dependency installation/build work
  --publish    strict gate plus canonical clean-tree publication check

Environment:
  QUALITY_BASE_REF                 override comparison base
  QUALITY_LOG_TAIL                 failure log lines to print (default: 80)
  QUALITY_FIX_MAX_PASSES           deterministic fix passes (default: 4)
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

LOG_TAIL="${QUALITY_LOG_TAIL:-80}"
FIX_MAX_PASSES="${QUALITY_FIX_MAX_PASSES:-4}"
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
CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "${CURRENT_BRANCH}" == "master" ]]; then
  printf '❌ QG_PROTECTED_BRANCH: agent workflow must not run/publish directly on master; use a dedicated branch and pull request\n' >&2
  exit 1
fi

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
  tail -n "${LOG_TAIL}" "${log}" >&2 || true
  rm -f "${log}"
  return "${rc}"
}

collect_changed_files() {
  {
    if [[ "${BASE_REF}" != "HEAD" ]] && git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=ACMR
    git diff --cached --name-only --diff-filter=ACMR
    git ls-files --others --exclude-standard
  } |
    awk 'NF' |
    sort -u |
    while IFS= read -r file; do
      [[ -f "${file}" ]] && printf '%s\n' "${file}"
    done
}

collect_deleted_files() {
  {
    if [[ "${BASE_REF}" != "HEAD" ]] && git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
      git diff --name-only --diff-filter=D "${BASE_REF}...HEAD"
    fi
    git diff --name-only --diff-filter=D
    git diff --cached --name-only --diff-filter=D
  } |
    awk 'NF' |
    sort -u
}

mapfile -t CHANGED_FILES < <(collect_changed_files)
mapfile -t DELETED_FILES < <(collect_deleted_files)

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
  for file in "${CHANGED_FILES[@]}"; do
    IFS= read -r first_line <"${file}" || true
    [[ "${first_line:-}" == '#!'* ]] || continue

    if git ls-files --error-unmatch -- "${file}" >/dev/null 2>&1; then
      mode="$(git ls-files --stage -- "${file}" | awk 'NR == 1 {print $1}')"
      if [[ "${mode}" != "100755" ]]; then
        printf '❌ QG_EXEC_BIT: %s has a shebang but Git mode is %s; run git add --chmod=+x %q\n' \
          "${file}" "${mode:-unknown}" "${file}" >&2
        exec_bit_failed=1
      fi
    elif [[ ! -x "${file}" ]]; then
      printf '❌ QG_EXEC_BIT: untracked %s has a shebang but is not executable\n' "${file}" >&2
      exec_bit_failed=1
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
    exit 1
  }
  run_compact "agent gate shell formatting" \
    pre-commit run shfmt-docker --files scripts/agent-quality-gate.sh
  run_compact "agent gate shell lint" \
    pre-commit run shell-lint --files scripts/agent-quality-gate.sh
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
  command -v python >/dev/null 2>&1 || {
    echo "❌ python is required" >&2
    exit 1
  }
  command -v pre-commit >/dev/null 2>&1 || {
    echo "❌ pre-commit is required; run 'mise run hooks' first" >&2
    exit 1
  }

  for ((pass = 1; pass <= FIX_MAX_PASSES; pass++)); do
    printf '🔁 deterministic fix pass %d/%d\n' "${pass}" "${FIX_MAX_PASSES}"
    run_compact "regenerate declared service topology" \
      python scripts/generate-service-topology.py
    run_compact "regenerate service consumers" \
      python scripts/generate-service-consumers.py

    mapfile -t CHANGED_FILES < <(collect_changed_files)
    if (("${#CHANGED_FILES[@]}" == 0)); then
      printf '✅ no changed files require formatter/linter fixes\n'
      exit 0
    fi

    before_fingerprint="$(worktree_fingerprint)"
    if run_compact "apply/check pre-commit hooks on changed files" \
      pre-commit run --hook-stage pre-commit \
      --files "${CHANGED_FILES[@]}" --show-diff-on-failure; then
      printf '✅ deterministic formatter/linter fixes converged in %d pass(es)\n' "${pass}"
      printf "ℹ️  review 'git diff' and 'git status --short', commit the result, then run this gate without --fix\n"
      exit 0
    fi

    mapfile -t CHANGED_FILES < <(collect_changed_files)
    after_fingerprint="$(worktree_fingerprint)"
    if [[ "${after_fingerprint}" == "${before_fingerprint}" ]]; then
      printf '❌ QG_FIX_STALLED: formatter/linter failed without changing files; fix the reported error instead of repeating identical passes\n' >&2
      exit 1
    fi
    if ((pass == FIX_MAX_PASSES)); then
      printf '❌ QG_FIX_NON_CONVERGENT: deterministic fixes did not converge after %d passes\n' "${FIX_MAX_PASSES}" >&2
      exit 1
    fi
    printf 'ℹ️  deterministic fixes changed files; rerunning the complete changed-file gate before build\n'
  done
fi

run_compact "declared service topology is synchronized" \
  python scripts/generate-service-topology.py --check
run_compact "Homarr/Gatus/AutoKuma consumers are synchronized" \
  python scripts/generate-service-consumers.py --check
run_compact "repository unit/contract tests" \
  python -m unittest discover -s tests -p 'test_*.py' -q

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
