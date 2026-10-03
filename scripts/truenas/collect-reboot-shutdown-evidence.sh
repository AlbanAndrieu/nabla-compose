#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${NABLA_REBOOT_EVIDENCE_DIR:-/mnt/cpool/var/nabla/reboot-evidence}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${OUTPUT_DIR}/${STAMP}"
PREVIOUS_BOOT="${NABLA_PREVIOUS_BOOT_OFFSET:--1}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run as root"
for command in journalctl systemctl midclt uname date install grep awk sed; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

install -d -m 0700 "${OUTPUT_DIR}" "${DEST}"

capture() {
  local name="$1"
  shift
  {
    printf '# command:'
    printf ' %q' "$@"
    printf '\n'
    "$@"
  } >"${DEST}/${name}.txt" 2>&1 || true
}

printf '%s\n' "$(date -Iseconds)" >"${DEST}/collected-at.txt"

capture current-boot-id midclt call system.boot_id
capture current-system-ready midclt call system.ready
capture current-system-state midclt call system.state
capture current-uname uname -a
capture current-failed-units systemctl --failed --no-pager

capture boot-list journalctl --list-boots --no-pager
capture previous-boot-full journalctl -b "${PREVIOUS_BOOT}" --no-pager -o short-precise
capture previous-boot-end journalctl -b "${PREVIOUS_BOOT}" -e --no-pager -o short-precise
capture previous-boot-errors journalctl -b "${PREVIOUS_BOOT}" -p warning..alert --no-pager -o short-precise
capture previous-shutdown-target journalctl -b "${PREVIOUS_BOOT}"   -u systemd-logind.service   -u middlewared.service   -u docker.service   -u libvirtd.service   -u virtqemud.service   -u zfs-mount.service   -u zfs.target   --no-pager -o short-precise

grep -Eai   'reboot|shutdown|poweroff|halt|stopp|timeout|timed out|failed|dependency|unmount|umount|zfs|middleware|docker|containerd|libvirt|qemu|watchdog|blocked for more than|hung task|I/O error|reset'   "${DEST}/previous-boot-full.txt"   >"${DEST}/previous-boot-focus.txt" || true

if command -v last >/dev/null 2>&1; then
  capture reboot-history last -x
fi

chmod -R go-rwx "${DEST}"
printf 'OK: reboot/shutdown evidence captured at %s\n' "${DEST}"
printf 'Review first: %s\n' "${DEST}/previous-boot-focus.txt"
