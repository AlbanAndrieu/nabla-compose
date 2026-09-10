#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

[[ -x "${ROOT}/scripts/truenas/audit-app-lifecycle.sh" ]] ||
  fail "missing TrueNAS lifecycle audit"
[[ -x "${ROOT}/scripts/talos/validate-cluster.sh" ]] ||
  fail "missing Talos/Kubernetes cluster validation"

printf '🔎 Standard TrueNAS platform diagnostic\n'
printf '   phase 1/2: TrueNAS application lifecycle\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/audit-app-lifecycle.sh"

printf '\n   phase 2/2: Talos/Kubernetes + PSA/PSS posture\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/talos/validate-cluster.sh"

printf '\n✅ Standard TrueNAS platform diagnostic passed: applications + Talos/Kubernetes + PSA/PSS\n'
