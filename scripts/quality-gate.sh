#!/usr/bin/env bash
set -euo pipefail

# Agent/human quality gate to run before every push.
# Pre-commit hooks may apply safe formatting/fixes. If they change tracked files,
# review and commit those changes, then run this gate again before pushing.

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

BASE_REF="${QUALITY_BASE_REF:-origin/master}"
if ! git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
  BASE_REF="HEAD~1"
fi

echo "🔧 Running repository formatters and linters on branch changes..."
pre-commit run \
  --hook-stage pre-commit \
  --from-ref "${BASE_REF}" \
  --to-ref HEAD \
  --show-diff-on-failure

echo "🔍 Checking whitespace errors..."
git diff --check

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Quality tools changed tracked files or staged changes remain."
  echo "   Review the changes, commit them, then run scripts/quality-gate.sh again."
  git status --short
  exit 1
fi

echo "✅ Quality gate passed; repository is clean and ready to push."
