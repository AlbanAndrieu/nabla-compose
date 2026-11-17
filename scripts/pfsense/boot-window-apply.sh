#!/usr/bin/env bash
# Apply the eMMC write diet in the few minutes a failing Netgate 1100 stays up after boot
# (docs/pfsense/incidents/2026-11-17-pfsense-userland-freeze.md). Run it in your own terminal:
# the SSH key asks for its passphrase. Power-cycle pfSense with the WAN UNPLUGGED (cold boot
# bridges LAN and WAN), start this script, and plug the WAN only when it asks.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target="${PFSENSE_SSH_TARGET:-admin@172.17.0.1}"
port="${PFSENSE_SSH_PORT:-9922}"
cm="${HOME}/.ssh/cm-${target}:${port}"
mkdir -p "${here}/../../logs"
out="${here}/../../logs/pfsense-boot-window-$(date +%Y%m%d-%H%M%S).log"
echo "waiting for the pfSense SSH banner on ${target#*@}:${port}..."
until timeout 3 bash -c "exec 3<>/dev/tcp/${target#*@}/${port} && head -c 8 <&3" 2>/dev/null | grep -q '^SSH-2.0'; do
  sleep 1
done
if ! ssh -O check -o ControlPath="${cm}" -p "${port}" "${target}" 2>/dev/null; then
  ssh -fN -o ControlMaster=yes -o ControlPersist=4h -o ControlPath="${cm}" \
    -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -p "${port}" "${target}"
fi
# Args: label, remote command, local script. A failed step is logged and the next one still runs.
run() {
  echo "==> $(date +%T) $1 $2" | tee -a "${out}"
  # shellcheck disable=SC2029 # the remote command is a fixed literal chosen by this script.
  ssh -o ControlPath="${cm}" -p "${port}" "${target}" "$2" <"${here}/$3" 2>&1 | sed "s/^/$1: /" | tee -a "${out}" ||
    echo "ERROR: $1 exited with ${PIPESTATUS[0]}" | tee -a "${out}"
}
# Most write-heavy first: the package restarts are what triggered the 17/11 freeze.
run hold "php -- apply" hold-packages-at-boot.php
run logging "php -- apply" stop-default-pass-logging.php
run rrd "php -- apply" disable-rrd-graphing.php
run hold "php -- check" hold-packages-at-boot.php
run logging "php -- check" stop-default-pass-logging.php
run rrd "php -- check" disable-rrd-graphing.php
run emmc "/bin/sh -s -- check" emmc-health.sh
read -r -p "Plug the WAN in, wait 30 s, then press Enter to install mmc-utils (writes to the eMMC), or Ctrl-C to stop here. " _
run emmc "/bin/sh -s -- apply" emmc-health.sh
echo "log: ${out}"
