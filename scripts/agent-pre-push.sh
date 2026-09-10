#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

status_before="$(git status --porcelain=v1)"
if [[ -n "${status_before}" ]]; then
  printf '❌ QG_PRE_PUSH_DIRTY: commit or stash local changes before the pre-push preparation gate\n' >&2
  printf '%s\n' "${status_before}" >&2
  exit 1
fi

bash scripts/agent-quality-gate.sh --fix

status_after_fix="$(git status --porcelain=v1)"
if [[ -n "${status_after_fix}" ]]; then
  printf '❌ QG_AUTOFIX_APPLIED: deterministic generators/formatters changed committed files before push\n' >&2
  printf '   Review the compact diff, amend/commit these deterministic fixes, then push again. Remote CI was not consumed.\n' >&2
  printf '%s\n' "${status_after_fix}" >&2
  exit 1
fi

bash scripts/agent-quality-gate.sh --publish
printf '✅ Local pre-push preparation gate passed: autofixers converged, full tests passed, and the tree is clean.\n'
