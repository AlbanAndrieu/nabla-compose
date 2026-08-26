#!/usr/bin/env bash
set -euo pipefail

# Agent/human quality gate to run before every push.
# Validate every file touched by the branch plus staged, unstaged, and untracked
# working-tree changes so formatters and validators run before CI sees them.

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BASE_REF="${QUALITY_BASE_REF:-origin/master}"
if ! git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
  BASE_REF="HEAD~1"
fi

mapfile -t CHANGED_FILES < <(
  {
    git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
    git diff --name-only --diff-filter=ACMR
    git diff --cached --name-only --diff-filter=ACMR
    git ls-files --others --exclude-standard
  } | awk 'NF' | sort -u
)

if ((${#CHANGED_FILES[@]} == 0)); then
  echo "✅ No changed files require validation."
  exit 0
fi

echo "🔧 Running repository formatters and linters on changed files..."
if ! pre-commit run \
  --hook-stage pre-commit \
  --files "${CHANGED_FILES[@]}" \
  --show-diff-on-failure; then
  echo "❌ Pre-commit changed files or found validation errors."
  echo "   Review/fix the output, then run scripts/quality-gate.sh again."
  git status --short
  exit 1
fi

echo "🔍 Checking whitespace errors..."
git diff --check
git diff --cached --check

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Quality tools changed tracked files or staged changes remain."
  echo "   Review the changes, commit them, then run scripts/quality-gate.sh again."
  git status --short
  exit 1
fi

echo "✅ Quality gate passed; repository is clean and ready to push."
