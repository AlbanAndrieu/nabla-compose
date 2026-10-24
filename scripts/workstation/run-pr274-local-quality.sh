#!/usr/bin/env bash
# Isolated local-first quality pass on exact Draft PR #274 HEAD.
# Never source: a failing subprocess must not terminate the operator shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'BLOCKED: execute with bash; do not source this runner.\n' >&2
  return 2
fi
set -Eeuo pipefail
umask 077
# Git hook environments can leak into an operator session. Ignore them here.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE

remote='https://github.com/AlbanAndrieu/nabla-compose.git'
branch='fix/homelab-operator-diagnostics-followup-20261024'
state="${NABLA_AGENT_STATE_DIR:-${HOME:-/nonexistent}/.local/share/nabla}"
cache="$state/git/nabla-compose.git"
worktree_base="$state/agent-worktrees"
reports="$state/quality-reports"
phase='init'
head='unresolved'
workspace=''
parent=''
report=''
first_failure='none'
pass_count=0
refresh_count=0

if (($#)); then
  printf 'Usage: bash scripts/workstation/run-pr274-local-quality.sh\n' >&2
  exit 2
fi
# Only synthetic offline tests may override the public Git remote.
if [[ "${NABLA_PR274_TEST_MODE:-0}" == 1 && -n "${NABLA_PR274_TEST_REMOTE:-}" ]]; then
  remote="$NABLA_PR274_TEST_REMOTE"
fi

status_report() {
  local rc=$?
  trap - EXIT
  printf '\nPR274_QUALITY_RESULT=%s\n' "$( ((rc==0)) && printf PASS || printf BLOCKED )"
  printf 'PR_HEAD=%s\n' "$head"
  printf 'GATES_PASSED=%d\n' "$pass_count"
  printf 'FIRST_FAILURE=%s\n' "$first_failure"
  printf 'EVIDENCE_DIR=%s\n' "$report"
  if [[ -n "$workspace" && -d "$workspace" ]]; then
    if [[ -n "$(git -C "$workspace" status --porcelain --untracked-files=normal 2>/dev/null || true)" ]]; then
      printf 'REVIEW_WORKTREE=%s\n' "$workspace"
      printf 'NEXT=Review generated diff; no files committed or pushed.\n'
    else
      # Safe cleanup: only a clean worktree created during this invocation.
      if flock -w 15 9; then
        if git --git-dir="$cache" worktree remove "$workspace" >/dev/null 2>&1; then
          rmdir "$parent" 2>/dev/null || true
        else
          printf 'PRESERVED_WORKTREE=%s (safe removal failed)\n' "$workspace"
        fi
        flock -u 9
      else
        printf 'PRESERVED_WORKTREE=%s (Git lock busy)\n' "$workspace"
      fi
    fi
  fi
  exit "$rc"
}
stop() {
  first_failure="$1"
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

trap status_report EXIT
[[ -n "${HOME:-}" && -d "$HOME" ]] || stop 'HOME unavailable'
(( EUID != 0 )) || [[ "${NABLA_PR274_TEST_MODE:-0}" == 1 ]] || stop 'run as non-root developer'
for program in git flock mktemp just; do
  command -v "$program" >/dev/null 2>&1 || stop "missing binary: $program"
done
for p in "$state" "$state/git" "$cache" "$worktree_base" "$reports"; do
  [[ ! -L "$p" ]] || stop "symlinked persistent path: $p"
done
mkdir -p -m 0700 -- "$state/git" "$worktree_base" "$reports" || stop 'persistent state not writable'
exec 9>"$state/.pr274-git.lock"
flock -w 20 9 || stop 'Git metadata lock busy'
if [[ ! -e "$cache" ]]; then
  git init --bare -q "$cache" || stop 'cannot initialize bare Git cache'
fi
[[ "$(git --git-dir="$cache" rev-parse --is-bare-repository 2>/dev/null)" == true ]] || stop 'invalid Git cache'

ref="refs/heads/$branch"
ref_output="$(git ls-remote --exit-code "$remote" "$ref" 2>/dev/null)" || stop 'GitHub branch lookup failed'
IFS=
# Record the exact published base, not HEAD~1. Full-PR destructive and mode
# contracts must be checked against master even in a detached worktree.
base_ref='refs/heads/master'
base_response="$(git ls-remote --exit-code "$remote" "$base_ref" 2>/dev/null)" || stop 'master ref lookup failed'
IFS=$'\t' read -r base_sha base_seen <<< "$base_response"
[[ "$base_sha" =~ ^[0-9a-f]{40}$ && "$base_seen" == "$base_ref" ]] || stop 'remote master ref invalid'
if ! git --git-dir="$cache" cat-file -e "$base_sha^{commit}" 2>/dev/null; then
  git --git-dir="$cache" fetch --no-tags --no-write-fetch-head "$remote" "$base_ref" >/dev/null 2>&1 || stop 'fetch of pinned master failed'
fi
git --git-dir="$cache" cat-file -e "$base_sha^{commit}" || stop 'pinned master SHA unavailable'
git --git-dir="$cache" merge-base --is-ancestor "$base_sha" "$head" || stop 'PR head does not contain current master'
export QUALITY_BASE_REF="$base_sha"
report="$(mktemp -d "$reports/pr274.XXXXXXXX")" || stop 'cannot create private report directory'
parent="$(mktemp -d "$worktree_base/pr274.XXXXXXXX")" || stop 'cannot create private worktree directory'
workspace="$parent/source"
trap 'first_failure="interrupted"; exit 130' INT TERM
if ! git --git-dir="$cache" worktree add --detach "$workspace" "$head" >"$report/worktree.log" 2>&1; then
  stop 'isolated Git worktree creation failed'
fi
flock -u 9
[[ "$(git -C "$workspace" rev-parse HEAD)" == "$head" ]] || stop 'snapshot SHA mismatch'
[[ -f "$workspace/.agents/skills/local-first-quality/SKILL.md" &&
   -f "$workspace/scripts/quality/python-with-repo-deps.sh" &&
   -f "$workspace/scripts/agent-quality-gate.sh" ]] || stop 'required scripts missing at PR HEAD'
# Reuse common status API once an exact pinned checkout exists.
# shellcheck source=../lib/common.sh
source "$workspace/scripts/lib/common.sh"
info "Pinned PR274 HEAD ${head:0:12}; operator checkout untouched"

step() {
  local label="$1" rc
  shift
  phase="$label"
  info "$label"
  if (cd "$workspace" && "$@") >"$report/$label.log" 2>&1; then
    pass_count=$((pass_count + 1))
    ok "$label"
    return 0
  else
    rc=$?
    warn "$label failed (exit $rc); private log: $report/$label.log"
    return "$rc"
  fi
}
# Only use dependency sources already present. If unavailable, sync pinned uv.lock
# in this ephemeral development worktree; never run mise lock / pip globally.
check_python() {
  local interpreter="$1"
  [[ -x "$interpreter" ]] || return 1
  "$interpreter" -c 'import yaml, pytest' >/dev/null 2>&1
}
python_env=''
for candidate in "$workspace/.venv" "${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"; do
  if check_python "$candidate/bin/python"; then python_env="$candidate"; break; fi
done
if [[ -z "$python_env" ]]; then
  command -v uv >/dev/null 2>&1 || stop 'no Python with PyYAML/pytest and uv is unavailable'
  export UV_PROJECT_ENVIRONMENT="$workspace/.venv"
  step 'uv-sync-frozen' uv sync --frozen --group dev || stop 'uv sync failed; no quality gates attempted'
  python_env="$workspace/.venv"
  check_python "$python_env/bin/python" || stop 'uv sync completed without PyYAML/pytest'
fi
export NABLA_TRUENAS_DEV_VENV="$python_env"
export UV_PROJECT_ENVIRONMENT="$workspace/.venv"
export PATH="$python_env/bin:$PATH"
step 'targeted-contracts' just topology-generator-test || stop 'targeted-contracts'
if step 'generator-check-initial' just topology-generators-check; then
  info 'All generated projections match declarative inputs'
else
  [[ -z "$(git -C "$workspace" status --porcelain --untracked-files=normal)" ]] || stop 'cannot regenerate: workspace changed before generation'
  # The detached snapshot is privately owned by this run. We do not call the
  # branch-only just refresh target; its guard correctly rejects detached HEAD.
  step 'generate-topology' bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-topology.py || stop 'generate-topology'
  step 'generate-consumers' bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-consumers.py || stop 'generate-consumers'
  step 'generate-backstage' bash scripts/quality/python-with-repo-deps.sh scripts/generate-catalog-v2-artifacts.py || stop 'generate-backstage'
  refresh_count=1
  step 'generator-check-after-fix' just topology-generators-check || stop 'generator-check-after-fix'
  # Refuse generated churn outside reviewed projection paths.
  while IFS= read -r file; do
    case "$file" in
      catalog/service-topology.json|catalog/services.json|catalog/generated/*|apps/homarr/generated/apps.json|apps/gatus/config/config.yml|apps/autokuma/static/generated-monitors.json) ;;
      *) stop "unexpected generated file: $file" ;;
    esac
  done < <(git -C "$workspace" status --porcelain --untracked-files=normal | cut -c4-)
fi
step 'agent-skills' just agent-skills-check || stop 'agent-skills'
step 'quality' just quality || stop 'quality'
info "Quality validation complete; generated batches=$refresh_count; no publication gate claimed"
\t' read -r observed_head seen_ref <<< "$ref_output"
[[ "$observed_head" =~ ^[0-9a-f]{40}$ && "$seen_ref" == "$ref" ]] || stop 'remote ref not a valid pinned SHA'
# The bootstrap pinned a SHA before the runner was downloaded. Preserve it
# even when another agent fast-forwards the branch during startup.
head="${NABLA_PR274_EXPECTED_SHA:-$observed_head}"
[[ "$head" =~ ^[0-9a-f]{40}$ ]] || stop 'invalid pinned PR commit'
unset NABLA_PR274_EXPECTED_SHA
if ! git --git-dir="$cache" cat-file -e "$observed_head^{commit}" 2>/dev/null ||
   ! git --git-dir="$cache" cat-file -e "$head^{commit}" 2>/dev/null; then
  git --git-dir="$cache" fetch --no-tags --no-write-fetch-head "$remote" "$ref" >/dev/null 2>&1 || stop 'fetch of pinned PR history failed'
fi
git --git-dir="$cache" cat-file -e "$observed_head^{commit}" || stop 'observed PR SHA not present in cache'
git --git-dir="$cache" cat-file -e "$head^{commit}" || stop 'bootstrap-pinned SHA not reachable on current branch'
if [[ "$head" != "$observed_head" ]]; then
  git --git-dir="$cache" merge-base --is-ancestor "$head" "$observed_head" ||
    stop 'PR branch diverged or force-pushed after bootstrap'
  printf 'INFO: PR advanced since bootstrap; testing immutable pinned SHA %.12s, latest observed %.12s\n' "$head" "$observed_head"
fi
# Record the exact published base, not HEAD~1. Full-PR destructive and mode
# contracts must be checked against master even in a detached worktree.
base_ref='refs/heads/master'
base_response="$(git ls-remote --exit-code "$remote" "$base_ref" 2>/dev/null)" || stop 'master ref lookup failed'
IFS=$'\t' read -r base_sha base_seen <<< "$base_response"
[[ "$base_sha" =~ ^[0-9a-f]{40}$ && "$base_seen" == "$base_ref" ]] || stop 'remote master ref invalid'
if ! git --git-dir="$cache" cat-file -e "$base_sha^{commit}" 2>/dev/null; then
  git --git-dir="$cache" fetch --no-tags --no-write-fetch-head "$remote" "$base_ref" >/dev/null 2>&1 || stop 'fetch of pinned master failed'
fi
git --git-dir="$cache" cat-file -e "$base_sha^{commit}" || stop 'pinned master SHA unavailable'
git --git-dir="$cache" merge-base --is-ancestor "$base_sha" "$head" || stop 'PR head does not contain current master'
export QUALITY_BASE_REF="$base_sha"
report="$(mktemp -d "$reports/pr274.XXXXXXXX")" || stop 'cannot create private report directory'
parent="$(mktemp -d "$worktree_base/pr274.XXXXXXXX")" || stop 'cannot create private worktree directory'
workspace="$parent/source"
trap 'first_failure="interrupted"; exit 130' INT TERM
if ! git --git-dir="$cache" worktree add --detach "$workspace" "$head" >"$report/worktree.log" 2>&1; then
  stop 'isolated Git worktree creation failed'
fi
flock -u 9
[[ "$(git -C "$workspace" rev-parse HEAD)" == "$head" ]] || stop 'snapshot SHA mismatch'
[[ -f "$workspace/.agents/skills/local-first-quality/SKILL.md" &&
   -f "$workspace/scripts/quality/python-with-repo-deps.sh" &&
   -f "$workspace/scripts/agent-quality-gate.sh" ]] || stop 'required scripts missing at PR HEAD'
# Reuse common status API once an exact pinned checkout exists.
# shellcheck source=../lib/common.sh
source "$workspace/scripts/lib/common.sh"
info "Pinned PR274 HEAD ${head:0:12}; operator checkout untouched"

step() {
  local label="$1" rc
  shift
  phase="$label"
  info "$label"
  if (cd "$workspace" && "$@") >"$report/$label.log" 2>&1; then
    pass_count=$((pass_count + 1))
    ok "$label"
    return 0
  else
    rc=$?
    warn "$label failed (exit $rc); private log: $report/$label.log"
    return "$rc"
  fi
}
# Only use dependency sources already present. If unavailable, sync pinned uv.lock
# in this ephemeral development worktree; never run mise lock / pip globally.
check_python() {
  local interpreter="$1"
  [[ -x "$interpreter" ]] || return 1
  "$interpreter" -c 'import yaml, pytest' >/dev/null 2>&1
}
python_env=''
for candidate in "$workspace/.venv" "${NABLA_TRUENAS_DEV_VENV:-${HOME}/.cache/nabla-compose/dev-venv}"; do
  if check_python "$candidate/bin/python"; then python_env="$candidate"; break; fi
done
if [[ -z "$python_env" ]]; then
  command -v uv >/dev/null 2>&1 || stop 'no Python with PyYAML/pytest and uv is unavailable'
  export UV_PROJECT_ENVIRONMENT="$workspace/.venv"
  step 'uv-sync-frozen' uv sync --frozen --group dev || stop 'uv sync failed; no quality gates attempted'
  python_env="$workspace/.venv"
  check_python "$python_env/bin/python" || stop 'uv sync completed without PyYAML/pytest'
fi
export NABLA_TRUENAS_DEV_VENV="$python_env"
export UV_PROJECT_ENVIRONMENT="$workspace/.venv"
export PATH="$python_env/bin:$PATH"
step 'targeted-contracts' just topology-generator-test || stop 'targeted-contracts'
if step 'generator-check-initial' just topology-generators-check; then
  info 'All generated projections match declarative inputs'
else
  [[ -z "$(git -C "$workspace" status --porcelain --untracked-files=normal)" ]] || stop 'cannot regenerate: workspace changed before generation'
  # The detached snapshot is privately owned by this run. We do not call the
  # branch-only just refresh target; its guard correctly rejects detached HEAD.
  step 'generate-topology' bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-topology.py || stop 'generate-topology'
  step 'generate-consumers' bash scripts/quality/python-with-repo-deps.sh scripts/generate-service-consumers.py || stop 'generate-consumers'
  step 'generate-backstage' bash scripts/quality/python-with-repo-deps.sh scripts/generate-catalog-v2-artifacts.py || stop 'generate-backstage'
  refresh_count=1
  step 'generator-check-after-fix' just topology-generators-check || stop 'generator-check-after-fix'
  # Refuse generated churn outside reviewed projection paths.
  while IFS= read -r file; do
    case "$file" in
      catalog/service-topology.json|catalog/services.json|catalog/generated/*|apps/homarr/generated/apps.json|apps/gatus/config/config.yml|apps/autokuma/static/generated-monitors.json) ;;
      *) stop "unexpected generated file: $file" ;;
    esac
  done < <(git -C "$workspace" status --porcelain --untracked-files=normal | cut -c4-)
fi
step 'agent-skills' just agent-skills-check || stop 'agent-skills'
step 'quality' just quality || stop 'quality'
info "Quality validation complete; generated batches=$refresh_count; no publication gate claimed"
