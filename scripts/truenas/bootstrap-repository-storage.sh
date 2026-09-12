#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
POOL="${NABLA_ZFS_POOL:-cpool}"
CANONICAL_MOUNT="/mnt/${POOL}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so ZFS datasets can be inspected/created"
for command in git grep sort zfs zpool; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
zpool list -H "${POOL}" >/dev/null 2>&1 || fail "ZFS pool ${POOL} does not exist"

mapfile -t mount_roots < <(
  grep -RhoE "${CANONICAL_MOUNT//\//\/}/[A-Za-z0-9._-]+" apps/*/compose.yml 2>/dev/null |
    sort -u
)

((${#mount_roots[@]} > 0)) || fail "no ${CANONICAL_MOUNT}/<dataset> references found in apps/*/compose.yml"

missing=0
printf 'Repository-declared TrueNAS dataset roots (%s):\n' "${POOL}"
for mount_root in "${mount_roots[@]}"; do
  dataset="${POOL}/${mount_root#"${CANONICAL_MOUNT}"/}"
  if zfs list -H -o name "${dataset}" >/dev/null 2>&1; then
    mountpoint="$(zfs get -H -o value mountpoint "${dataset}")"
    printf '✅ %-36s mountpoint=%s\n' "${dataset}" "${mountpoint}"
    continue
  fi

  missing=$((missing + 1))
  if [[ "${MODE}" == "--check" ]]; then
    printf '❌ %-36s missing (declared by repository Compose)\n' "${dataset}"
    continue
  fi

  printf 'Creating missing dataset %s...\n' "${dataset}"
  zfs create -p "${dataset}"
  zfs list -H -o name "${dataset}" >/dev/null 2>&1 || fail "dataset ${dataset} was not visible after creation"
  mountpoint="$(zfs get -H -o value mountpoint "${dataset}")"
  [[ "${mountpoint}" == "${mount_root}" ]] ||
    fail "dataset ${dataset} mounted at ${mountpoint}, expected ${mount_root}"
  printf '✅ %-36s created mountpoint=%s\n' "${dataset}" "${mountpoint}"
done

if [[ "${MODE}" == "--check" && ${missing} -gt 0 ]]; then
  printf '❌ %d repository-declared dataset root(s) are missing.\n' "${missing}" >&2
  printf '   Apply with: sudo bash scripts/truenas/bootstrap-repository-storage.sh --apply\n' >&2
  exit 1
fi

printf '✅ repository-declared TrueNAS dataset roots are present (%d checked).\n' "${#mount_roots[@]}"
