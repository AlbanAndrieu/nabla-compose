#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

require_commands git bash sudo midclt tr
ROOT="$(git rev-parse --show-toplevel)"
STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"

[[ -x "${ROOT}/scripts/truenas/audit-app-lifecycle.sh" ]] ||
  fail "missing TrueNAS lifecycle audit"
[[ -x "${ROOT}/scripts/truenas/reconcile-reboot-resume.sh" ]] ||
  fail "missing reboot resume reconciler"
[[ -x "${ROOT}/scripts/truenas/diagnose-docker-orphan-shims.sh" ]] ||
  fail "missing Docker/containerd orphan-shim diagnostic"
[[ -x "${ROOT}/scripts/talos/validate-cluster.sh" ]] ||
  fail "missing Talos/Kubernetes cluster validation"
[[ -x "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" ]] ||
  fail "missing TrueNAS CSI orphan diagnostic"

printf '🔎 Standard TrueNAS platform diagnostic\n'
printf '   phase 1/5: TrueNAS application lifecycle + functional probes\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/audit-app-lifecycle.sh"

printf '\n   phase 2/5: frozen reboot resume manifest acceptance\n'
if [[ -f "${STATE_ROOT}/latest" ]]; then
  state_dir="$(cat "${STATE_ROOT}/latest")"
  if [[ -f "${state_dir}/boot-id-before" ]]; then
    before_boot_id="$(cat "${state_dir}/boot-id-before")"
    current_boot_id="$(sudo midclt call system.boot_id | tr -d '"')"
    if [[ "${current_boot_id}" != "${before_boot_id}" ]]; then
      sudo bash "${ROOT}/scripts/truenas/reconcile-reboot-resume.sh" --check
    else
      printf 'SKIP: latest reboot manifest belongs to the current boot; post-reboot resume acceptance is not applicable yet\n'
    fi
  else
    warn "latest reboot state directory has no boot-id-before: ${state_dir}"
  fi
else
  printf 'SKIP: no reboot resume manifest exists under %s\n' "${STATE_ROOT}"
fi

printf '\n   phase 3/5: Docker/containerd orphan-shim inventory\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  sudo bash "${ROOT}/scripts/truenas/diagnose-docker-orphan-shims.sh" --check

printf '\n   phase 4/5: Talos/Kubernetes + PSA/PSS posture\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/talos/validate-cluster.sh"

printf '\n   phase 5/5: TrueNAS CSI dynamic dataset/orphan inventory\n'
DIAGNOSTIC_FULL_OUTPUT=1 \
  bash "${ROOT}/scripts/truenas/diagnose-csi-orphans.sh" --check

printf '\n✅ Standard TrueNAS platform diagnostic passed: applications + functional probes + reboot resume acceptance + Docker/containerd runtime + Talos/Kubernetes + PSA/PSS + CSI dataset inventory\n'
