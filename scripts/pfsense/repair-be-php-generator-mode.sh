#!/bin/sh
# Restore the 0755 mode of /etc/rc.php_ini_setup in boot environments (all of them by default).
# harden-pfsense-php-fpm.sh (before 2026-11-15) copied a 0600 mktemp file over it; pfSense-rc
# executes it directly, so every later boot of that BE stalled and fell back to another BE.
# Run from the workstation, check first, then apply (check-drift.sh runs the check):
#   ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check [BE...] < scripts/pfsense/repair-be-php-generator-mode.sh
set -eu
mode="${1:-check}"
if [ "${mode}" != check ] && [ "${mode}" != apply ]; then
  echo "usage: check|apply [BE...]" >&2
  exit 2
fi
[ "$#" -gt 0 ] && shift
# shellcheck disable=SC2046 # BE names never contain spaces: one word per boot environment.
[ "$#" -gt 0 ] || set -- $(bectl list -H | awk '{ print $1 }')
opts=ro
[ "${mode}" = apply ] && opts=rw
mp="/tmp/be-php-generator.$$"
trap 'umount "${mp}" 2>/dev/null || true; rmdir "${mp}" 2>/dev/null || true' EXIT
changes=0
for be in "$@"; do
  active=$(bectl list -H | awk -v b="${be}" '$1 == b { print $2 }')
  root="${mp}"
  case "${active}" in
    '') echo "ERROR: boot environment ${be} not found" >&2; exit 1 ;;
    *N*) root="" ;;
    *) mkdir "${mp}"; mount -t zfs -o "${opts}" "pfSense/ROOT/${be}" "${mp}" ;;
  esac
  f="${root}/etc/rc.php_ini_setup"
  if [ -x "${f}" ]; then
    echo "OK: ${be} rc.php_ini_setup mode=$(stat -f %Lp "${f}")"
  else
    changes=$((changes + 1))
    echo "CHANGE: ${be} rc.php_ini_setup mode=$(stat -f %Lp "${f}") expected=755"
    if [ "${mode}" = apply ]; then
      chmod 0755 "${f}"
      echo "OK: ${be} rc.php_ini_setup mode=$(stat -f %Lp "${f}")"
    fi
  fi
  if [ -n "${root}" ]; then
    umount "${mp}"
    rmdir "${mp}"
  fi
done
echo "summary: ${changes} boot environment(s) with a non-executable generator, mode=${mode}"
