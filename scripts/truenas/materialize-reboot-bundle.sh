#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

REPO_ROOT="${NABLA_REPO_ROOT:-/mnt/cpool/compose/nabla-compose}"
BUNDLE_ROOT="${NABLA_REBOOT_BUNDLE_ROOT:-/mnt/cpool/tools/nabla-reboot}"
REF="HEAD"
ACTIVATE=0

usage() {
  cat <<'EOF'
usage: sudo bash scripts/truenas/materialize-reboot-bundle.sh [--ref <git-ref>] [--activate]

Builds an immutable reboot bundle from one exact Git commit, verifies it, and
optionally updates /mnt/cpool/tools/nabla-reboot/current atomically.
EOF
}

while (($#)); do
  case "$1" in
    --ref)
      shift
      [[ $# -gt 0 ]] || { usage >&2; exit 2; }
      REF="$1"
      ;;
    --activate)
      ACTIVATE=1
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

require_root "run as root on TrueNAS"
require_commands git install mktemp sha256sum grep bash python3 mv awk cmp
[[ -d "${REPO_ROOT}/.git" ]] || fail "repository not found: ${REPO_ROOT}"

mkdir -p "${BUNDLE_ROOT}"
chmod 700 "${BUNDLE_ROOT}"

COMMIT="$(git -C "${REPO_ROOT}" rev-parse --verify "${REF}^{commit}")"
FINAL="${BUNDLE_ROOT}/${COMMIT}"
STAGE="$(mktemp -d "${BUNDLE_ROOT}/.${COMMIT}.tmp.XXXXXX")"
trap 'rm -rf "${STAGE}"' EXIT

FILES=(
  catalog/services.json
  catalog/service-topology.json
  scripts/lib/common.sh
  scripts/truenas/plan-app-lifecycle-order.py
  scripts/truenas/reconcile-talos-vm-policy.sh
  scripts/truenas/migrate-docker-address-pool.sh
  scripts/truenas/audit-docker-network-migration.sh
  scripts/truenas/diagnose-docker-orphan-shims.sh
  scripts/truenas/diagnose-csi-orphans.sh
  scripts/truenas/reboot-homelab.sh
)

materialize_file() {
  local path="$1" mode=0644 tmp
  case "${path}" in
    scripts/truenas/*.sh | scripts/truenas/*.py) mode=0755 ;;
  esac
  install -d -m 0755 "${STAGE}/$(dirname -- "${path}")"
  tmp="$(mktemp)"
  git -C "${REPO_ROOT}" show "${COMMIT}:${path}" >"${tmp}"
  install -m "${mode}" "${tmp}" "${STAGE}/${path}"
  rm -f "${tmp}"
}

validate_stage() {
  local path
  for path in "${FILES[@]}"; do
    [[ "${path}" == *.sh ]] && bash -n "${STAGE}/${path}"
  done

  python3 -m py_compile "${STAGE}/scripts/truenas/plan-app-lifecycle-order.py"
  rm -rf "${STAGE}/scripts/truenas/__pycache__"

  grep -q -- '--continue-prepare' "${STAGE}/scripts/truenas/reboot-homelab.sh" ||
    fail "materialized reboot script lacks --continue-prepare"
}

verify_bundle() {
  local bundle="$1"
  [[ -f "${bundle}/SOURCE_COMMIT" ]] || fail "bundle has no SOURCE_COMMIT: ${bundle}"
  [[ "$(cat "${bundle}/SOURCE_COMMIT")" == "${COMMIT}" ]] ||
    fail "bundle identity mismatch: ${bundle}"
  [[ -f "${bundle}/SHA256SUMS" ]] || fail "bundle has no SHA256SUMS: ${bundle}"
  (cd "${bundle}" && sha256sum --quiet -c SHA256SUMS) ||
    fail "bundle checksum mismatch: ${bundle}"
}

for path in "${FILES[@]}"; do
  materialize_file "${path}"
done
validate_stage

printf '%s\n' "${COMMIT}" >"${STAGE}/SOURCE_COMMIT"
(
  cd "${STAGE}"
  sha256sum "${FILES[@]}" >SHA256SUMS
  sha256sum --quiet -c SHA256SUMS
)

if [[ -e "${FINAL}" ]]; then
  verify_bundle "${FINAL}"
  cmp -s "${STAGE}/SHA256SUMS" "${FINAL}/SHA256SUMS" ||
    fail "existing bundle contents do not match commit ${COMMIT}; refusing silent overwrite"
  rm -rf "${STAGE}"
  trap - EXIT
  ok "verified existing immutable bundle ${FINAL}"
else
  mv "${STAGE}" "${FINAL}"
  trap - EXIT
  ok "materialized immutable bundle ${FINAL}"
fi

if ((ACTIVATE)); then
  pointer_tmp="$(mktemp "${BUNDLE_ROOT}/.current.XXXXXX")"
  printf '%s\n' "${FINAL}" >"${pointer_tmp}"
  chmod 0644 "${pointer_tmp}"
  mv "${pointer_tmp}" "${BUNDLE_ROOT}/current"
  ok "activated ${FINAL}"
fi

printf 'SOURCE_COMMIT=%s\n' "${COMMIT}"
printf 'BUNDLE=%s\n' "${FINAL}"
printf 'SCRIPT_SHA256=%s\n' "$(sha256sum "${FINAL}/scripts/truenas/reboot-homelab.sh" | awk '{print $1}')"
