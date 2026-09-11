#!/usr/bin/env bash
set -euo pipefail

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

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: run as root on TrueNAS" >&2; exit 1; }
for command in git install mktemp sha256sum grep bash python3 mv awk cmp; do
  command -v "${command}" >/dev/null 2>&1 || { echo "ERROR: ${command} is required" >&2; exit 1; }
done
[[ -d "${REPO_ROOT}/.git" ]] || { echo "ERROR: repository not found: ${REPO_ROOT}" >&2; exit 1; }

mkdir -p "${BUNDLE_ROOT}"
chmod 700 "${BUNDLE_ROOT}"

COMMIT="$(git -C "${REPO_ROOT}" rev-parse --verify "${REF}^{commit}")"
FINAL="${BUNDLE_ROOT}/${COMMIT}"
STAGE="$(mktemp -d "${BUNDLE_ROOT}/.${COMMIT}.tmp.XXXXXX")"
trap 'rm -rf "${STAGE}"' EXIT

FILES=(
  catalog/services.json
  catalog/service-topology.json
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
    scripts/*.sh | scripts/*.py) mode=0755 ;;
  esac
  install -d -m 0755 "${STAGE}/$(dirname -- "${path}")"
  tmp="$(mktemp)"
  git -C "${REPO_ROOT}" show "${COMMIT}:${path}" >"${tmp}"
  install -m "${mode}" "${tmp}" "${STAGE}/${path}"
  rm -f "${tmp}"
}

for path in "${FILES[@]}"; do
  materialize_file "${path}"
done

bash -n "${STAGE}/scripts/truenas/reboot-homelab.sh"
bash -n "${STAGE}/scripts/truenas/diagnose-docker-orphan-shims.sh"
bash -n "${STAGE}/scripts/truenas/diagnose-csi-orphans.sh"
python3 -m py_compile "${STAGE}/scripts/truenas/plan-app-lifecycle-order.py"
rm -rf "${STAGE}/scripts/truenas/__pycache__"
grep -q -- '--continue-prepare' "${STAGE}/scripts/truenas/reboot-homelab.sh" || {
  echo "ERROR: materialized reboot script lacks --continue-prepare" >&2
  exit 1
}

printf '%s\n' "${COMMIT}" >"${STAGE}/SOURCE_COMMIT"
(
  cd "${STAGE}"
  sha256sum "${FILES[@]}" >SHA256SUMS
  sha256sum --quiet -c SHA256SUMS
)

if [[ -e "${FINAL}" ]]; then
  [[ -f "${FINAL}/SOURCE_COMMIT" ]] || {
    echo "ERROR: existing bundle has no SOURCE_COMMIT: ${FINAL}" >&2
    exit 1
  }
  [[ "$(cat "${FINAL}/SOURCE_COMMIT")" == "${COMMIT}" ]] || {
    echo "ERROR: existing bundle identity mismatch: ${FINAL}" >&2
    exit 1
  }
  [[ -f "${FINAL}/SHA256SUMS" ]] || {
    echo "ERROR: existing bundle has no SHA256SUMS: ${FINAL}" >&2
    exit 1
  }
  (
    cd "${FINAL}"
    sha256sum --quiet -c SHA256SUMS
  ) || {
    echo "ERROR: existing bundle checksum mismatch; refusing silent overwrite: ${FINAL}" >&2
    exit 1
  }
  cmp -s "${STAGE}/SHA256SUMS" "${FINAL}/SHA256SUMS" || {
    echo "ERROR: existing bundle contents do not match commit ${COMMIT}; refusing silent overwrite" >&2
    exit 1
  }
  rm -rf "${STAGE}"
  trap - EXIT
  echo "OK: verified existing immutable bundle ${FINAL}"
else
  mv "${STAGE}" "${FINAL}"
  trap - EXIT
  echo "OK: materialized immutable bundle ${FINAL}"
fi

if ((ACTIVATE)); then
  pointer_tmp="$(mktemp "${BUNDLE_ROOT}/.current.XXXXXX")"
  printf '%s\n' "${FINAL}" >"${pointer_tmp}"
  chmod 0644 "${pointer_tmp}"
  mv "${pointer_tmp}" "${BUNDLE_ROOT}/current"
  echo "OK: activated ${FINAL}"
fi

printf 'SOURCE_COMMIT=%s\n' "${COMMIT}"
printf 'BUNDLE=%s\n' "${FINAL}"
printf 'SCRIPT_SHA256=%s\n' "$(sha256sum "${FINAL}/scripts/truenas/reboot-homelab.sh" | awk '{print $1}')"
