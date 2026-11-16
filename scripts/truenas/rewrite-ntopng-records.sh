#!/usr/bin/env bash
# Rewrite ntopng's files so they pick up the dataset's 16K recordsize.
# A recordsize change only applies to blocks written afterwards; RRD files are
# updated in place forever, so they keep 128K records until copied once.
#
#   bash scripts/truenas/rewrite-ntopng-records.sh --check   (read-only)
#   sudo bash scripts/truenas/rewrite-ntopng-records.sh --apply
#
# --apply stops ntopng, rewrites every regular file through read/write (cat,
# never cp: copy_file_range would clone the old blocks), keeps owner, mode and
# mtime, then starts ntopng again. Snapshots keep the old blocks until expiry.
set -euo pipefail

MODE="${1:---check}"
DATASET="${NTOPNG_DATASET:-cpool/ntopng}"
MOUNT="${NTOPNG_MOUNT:-/mnt/${DATASET}}"
MARKER="${NTOPNG_REWRITE_MARKER:-/mnt/cpool/var/nabla/ntopng-recordsize-16K.done}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

recordsize="$(zfs get -H -o value recordsize "${DATASET}")"
files="$(find "${MOUNT}" -xdev -type f | wc -l)"
printf 'dataset=%s recordsize=%s files=%s\n' "${DATASET}" "${recordsize}" "${files}"
if [[ -e "${MARKER}" ]]; then
  printf '✅ already rewritten: %s\n' "$(cat "${MARKER}")"
  exit 0
fi
[[ "${recordsize}" == "16K" ]] ||
  fail "recordsize is ${recordsize}; run bootstrap-repository-storage.sh --apply ntopng first"
if [[ "${MODE}" == "--check" ]]; then
  printf '⚠️  %s files still use the old recordsize; rewrite with --apply\n' "${files}"
  exit 0
fi
[[ "${EUID}" -eq 0 ]] || fail "--apply requires root"

app_list="$(mktemp)"
trap 'rm -f "${app_list}"' EXIT
printf 'ntopng\n' >"${app_list}"
NABLA_OPTIONAL_APPS_FILE="${app_list}" bash "${ROOT}/scripts/truenas/restore-optional-apps.sh" --stop

rewritten=0
while IFS= read -r -d '' file; do
  tmp="${file}.nabla-rewrite"
  cat -- "${file}" >"${tmp}"
  chown --reference="${file}" -- "${tmp}"
  chmod --reference="${file}" -- "${tmp}"
  touch --reference="${file}" -- "${tmp}"
  mv -f -- "${tmp}" "${file}"
  rewritten=$((rewritten + 1))
done < <(find "${MOUNT}" -xdev -type f ! -name '*.nabla-rewrite' -print0)

NABLA_OPTIONAL_APPS_FILE="${app_list}" bash "${ROOT}/scripts/truenas/restore-optional-apps.sh" --start
mkdir -p -- "$(dirname -- "${MARKER}")"
printf '%s files on %s\n' "${rewritten}" "$(date -u +%FT%TZ)" >"${MARKER}"
printf '✅ rewrote %s files; ntopng started again\n' "${rewritten}"
