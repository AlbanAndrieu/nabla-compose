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
[[ -x "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" ]] ||
  fail "missing TrueNAS CSI orphan diagnostic"

printf '🔎 Standard TrueNAS platform diagnostic\n'
printf '   phase 1/3: TrueNAS application lifecycle\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/audit-app-lifecycle.sh"

printf '\n   phase 2/3: Talos/Kubernetes + PSA/PSS posture\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/talos/validate-cluster.sh"

printf '\n   phase 3/3: TrueNAS CSI dynamic dataset/orphan inventory\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" --check

printf '\n✅ Standard TrueNAS platform diagnostic passed: applications + Talos/Kubernetes + PSA/PSS + CSI dataset inventory\n'
