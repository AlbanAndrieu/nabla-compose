#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

[[ -x "${ROOT}/scripts/truenas/audit-app-lifecycle.sh" ]] ||
  fail "missing TrueNAS lifecycle audit"
[[ -x "${ROOT}/scripts/truenas/diagnose-docker-orphan-shims.sh" ]] ||
  fail "missing Docker/containerd orphan-shim diagnostic"
[[ -x "${ROOT}/scripts/talos/validate-cluster.sh" ]] ||
  fail "missing Talos/Kubernetes cluster validation"
[[ -x "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" ]] ||
  fail "missing TrueNAS CSI orphan diagnostic"

printf '🔎 Standard TrueNAS platform diagnostic\n'
printf '   phase 1/4: TrueNAS application lifecycle\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/audit-app-lifecycle.sh"

printf '\n   phase 2/4: Docker/containerd orphan-shim inventory\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  sudo bash "${ROOT}/scripts/truenas/diagnose-docker-orphan-shims.sh" --check

printf '\n   phase 3/4: Talos/Kubernetes + PSA/PSS posture\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/talos/validate-cluster.sh"

printf '\n   phase 4/4: TrueNAS CSI dynamic dataset/orphan inventory\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" --check

printf '\n✅ Standard TrueNAS platform diagnostic passed: applications + Docker/containerd runtime + Talos/Kubernetes + PSA/PSS + CSI dataset inventory\n'
