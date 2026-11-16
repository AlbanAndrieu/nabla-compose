#!/bin/sh
# Keep boot environments out of the fallback: after a failed boot pfSense activates the OLDEST non-active
# BE without pfsense:failed=yes, and a successful one-shot boot clears that flag. On 2026-11-15 the 26.07
# BE passed its boot test, then its GUI and SSH stalled after an hour: it must not be the fallback.
# pfSense clears the flag again at the next successful boot of that BE (the next 26.07 attempt).
# Run from the workstation, check first, then apply (check-drift.sh runs the check):
#   ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check BE... < scripts/pfsense/exclude-be-from-fallback.sh
set -eu
mode="${1:-}"
if [ "$#" -lt 2 ] || { [ "${mode}" != check ] && [ "${mode}" != apply ]; }; then
  echo "usage: check|apply BE..." >&2
  exit 2
fi
shift
changes=0
for be in "$@"; do
  flags=$(bectl list -H | awk -v b="${be}" '$1 == b { print $2 }')
  case "${flags}" in
    '') echo "ERROR: boot environment ${be} not found" >&2; exit 1 ;;
    *N*) echo "ERROR: ${be} is the running boot environment" >&2; exit 1 ;;
    *) ;;
  esac
  failed=$(zfs get -H -o value pfsense:failed "pfSense/ROOT/${be}")
  if [ "${failed}" = yes ]; then
    echo "OK: ${be} pfsense:failed=yes (excluded from the fallback)"
    continue
  fi
  changes=$((changes + 1))
  echo "CHANGE: ${be} pfsense:failed=${failed} expected=yes"
  if [ "${mode}" = apply ]; then
    zfs set pfsense:failed=yes "pfSense/ROOT/${be}"
    echo "OK: ${be} pfsense:failed=yes"
  fi
done
echo "summary: ${changes} boot environment(s) eligible as fallback before this run, mode=${mode}"
