# shellcheck shell=bash
set -euo pipefail

# Dependency-free L1 syntax gate for disconnected workspaces.
# This never replaces agent-pre-push, pre-commit, Betterleaks or remote CI.
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
MAX_PATHS="${AGENT_OFFLINE_MAX_PATHS:-0}"
[[ "$MAX_PATHS" =~ ^(0|[1-9][0-9]*)$ ]] || {
  echo "ERROR: AGENT_OFFLINE_MAX_PATHS must be a nonnegative integer" >&2
  exit 2
}
BASE="${QUALITY_BASE_REF:-}"
if [[ -z "$BASE" ]]; then
  for candidate in origin/master origin/main master main; do
    if git rev-parse --verify "$candidate^{commit}" >/dev/null 2>&1; then
      BASE="$candidate"
      break
    fi
  done
fi
declare -a files=()
# Do not let a failing git diff silently turn into an empty, passing scan:
# mapfile/process substitution would otherwise hide the producer's exit code.
if [[ -n "$BASE" ]] && git rev-parse --verify "$BASE^{commit}" >/dev/null 2>&1 &&
  git merge-base "$BASE" HEAD >/dev/null 2>&1 &&
  git diff --name-only --diff-filter=ACMR "$BASE...HEAD" >/dev/null 2>&1; then
  mapfile -t files < <(
    { git diff --name-only --diff-filter=ACMR "$BASE...HEAD"
      git diff --name-only --diff-filter=ACMR
      git diff --cached --name-only --diff-filter=ACMR
      git ls-files --others --exclude-standard
    } | LC_ALL=C sort -u
  )
else
  printf 'WARNING: offline Git base missing; checking all tracked + local files, not PR completeness\n' >&2
  mapfile -t files < <(
    { git ls-files
      git ls-files --others --exclude-standard
    } | LC_ALL=C sort -u
  )
fi
if ((MAX_PATHS > 0 && ${#files[@]} > MAX_PATHS)); then
  printf 'ERROR: offline scope %d exceeds maximum %d; narrow the change or adjust AGENT_OFFLINE_MAX_PATHS\n' "${#files[@]}" "$MAX_PATHS" >&2
  exit 2
fi
command -v python3 >/dev/null || { echo 'ERROR: python3 is required' >&2; exit 2; }
checked=0
declare -a python_files=()
for file in "${files[@]}"; do
  [[ -f "$file" && ! -L "$file" ]] || continue
  case "$file" in
    *.sh)
      bash -n "$file"
      checked=$((checked + 1))
      ;;
    *.py)
      python_files+=("$file")
      ;;
  esac
done
if (("${#python_files[@]}" > 0)); then
  python3 - "${python_files[@]}" <<'PY'
import ast
from pathlib import Path
import sys

for name in sys.argv[1:]:
    ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
PY
  checked=$((checked + ${#python_files[@]}))
fi
git diff --check
git diff --cached --check
printf 'OK: offline L1 syntax + whitespace checks passed, files=%d, parsed=%d\n' "${#files[@]}" "$checked"
printf '%s\n' 'NOT VERIFIED: hooks, formatters, dependencies, security scanners, full pytest and publication gate'
