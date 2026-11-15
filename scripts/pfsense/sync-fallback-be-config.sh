#!/bin/sh
# Copy the running config.xml into the fallback boot environment. After a failed boot pfSense
# activates the OLDEST non-active BE without pfsense:failed=yes; on 2026-11-15 that BE held a
# June config (GUI 10443 open to the Internet). Re-run after every reviewed config change.
# Run from the workstation, check first, then apply:
#   ssh -p 9922 admin@172.17.0.1 /bin/sh -s -- check default < scripts/pfsense/sync-fallback-be-config.sh
# Packages missing in the fallback BE (RESTAPI, crowdsec on 2026-11-15) reinstall at its first boot.
set -eu
mode="${1:-}"
be="${2:-}"
if [ -z "${be}" ] || { [ "${mode}" != check ] && [ "${mode}" != apply ]; }; then
  echo "usage: check|apply BE" >&2
  exit 2
fi
active=$(bectl list -H | awk '$2 ~ /N/ { print $1 }')
[ "${be}" != "${active}" ] || { echo "ERROR: ${be} is the running boot environment" >&2; exit 1; }
bectl list -H | awk -v b="${be}" '$1 == b { found=1 } END { exit !found }' || {
  echo "ERROR: boot environment ${be} not found" >&2
  exit 1
}

# Same order as _be_recent_name in /etc/rc.be_functions.sh.
target=""
for name in $(bectl list -H -C creation | awk '{ print $1 }'); do
  [ "${name}" = "${active}" ] && continue
  [ "$(zfs get -H -o value pfsense:failed "pfSense/ROOT/${name}")" = yes ] && continue
  target="${name}"
  break
done
echo "running=${active} fallback_target=${target:-none}"
[ "${target}" = "${be}" ] || echo "WARN: ${be} is not the current fallback target"

opts=ro
[ "${mode}" = apply ] && opts=rw
mp="/tmp/be-cf.$$"
trap 'umount "${mp}" 2>/dev/null || true; rmdir "${mp}" 2>/dev/null || true' EXIT
mkdir "${mp}"
mount -t zfs -o "${opts}" "pfSense/ROOT/${be}/cf" "${mp}"
src=/cf/conf/config.xml
dst="${mp}/conf/config.xml"
revision() {
  awk '/<revision>/ { r = 1 } r && /<time>/ { gsub(/.*<time>|<\/time>.*/, ""); print strftime("%Y-%m-%d %H:%M", $0); exit }' "$1"
}
src_rev=$(revision "${src}")
dst_rev=$(revision "${dst}")
src_sum=$(sha256 -q "${src}")
dst_sum=$(sha256 -q "${dst}")
if [ "${src_sum}" = "${dst_sum}" ]; then
  echo "OK: ${be} config.xml matches the running config (revision ${src_rev})"
  exit 0
fi
echo "CHANGE: ${be} config.xml revision ${dst_rev} differs from running revision ${src_rev}"
[ "${mode}" = apply ] || exit 0
cp -p "${dst}" "${mp}/conf/config.xml.nabla-pre-sync-$(date +%Y%m%d%H%M%S)"
# Rewrite in place: keeps the target file's owner and mode.
cat "${src}" >"${dst}"
[ "$(sha256 -q "${dst}")" = "${src_sum}" ] || { echo "ERROR: copy verification failed" >&2; exit 1; }
echo "OK: ${be} config.xml now matches the running config (revision ${src_rev}); previous copy kept"
