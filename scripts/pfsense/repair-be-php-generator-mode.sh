#!/bin/sh
# Restore the 0755 mode of /etc/rc.php_ini_setup in inactive boot environments.
# harden-pfsense-php-fpm.sh (before 2026-11-15) copied a 0600 mktemp file over it; pfSense-rc
# executes it directly, so every later boot of that BE stalled and fell back to another BE.
# Run from the workstation, check first, then apply:
#   ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check BE... < scripts/pfsense/repair-be-php-generator-mode.sh
# The running BE is fixed with `chmod 0755 /etc/rc.php_ini_setup` through harden-pfsense-php-fpm.sh --check.
set -eu
mode="${1:-check}"
if [ "$#" -lt 2 ] || { [ "${mode}" != check ] && [ "${mode}" != apply ]; }; then
  echo "usage: check|apply BE..." >&2
  exit 2
fi
shift
opts=ro
[ "${mode}" = apply ] && opts=rw
mp="/tmp/be-php-generator.$$"
trap 'umount "${mp}" 2>/dev/null || true; rmdir "${mp}" 2>/dev/null || true' EXIT
changes=0
for be in "$@"; do
  active=$(bectl list -H | awk -v b="${be}" '$1 == b { print $2 }')
  case "${active}" in
    '') echo "ERROR: boot environment ${be} not found" >&2; exit 1 ;;
    *N*) echo "SKIP: ${be} is running; use harden-pfsense-php-fpm.sh --check" ; continue ;;
    *) ;;
  esac
  mkdir "${mp}"
  mount -t zfs -o "${opts}" "pfSense/ROOT/${be}" "${mp}"
  f="${mp}/etc/rc.php_ini_setup"
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
  umount "${mp}"
  rmdir "${mp}"
done
echo "summary: ${changes} boot environment(s) with a non-executable generator, mode=${mode}"
