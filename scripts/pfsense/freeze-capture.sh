#!/usr/bin/env bash
# Flight recorder for the pfSense userland freezes (docs/pfsense/incidents/2026-11-17-pfsense-userland-freeze.md).
# No serial console is reachable and sshd stops answering ~25 s after it comes up, so: wait for the
# real SSH banner after a reboot, authenticate at once (YubiKey PIN + touch), then stream read-only
# snapshots to the workstation. An already-open session should keep streaming through the freeze,
# since the remote part writes nothing on pfSense and never calls syslog.
# Usage: bash scripts/pfsense/freeze-capture.sh [OUTPUT_FILE]   then reboot pfSense.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="${1:-logs/pfsense-freeze-$(date +%Y%m%d-%H%M%S).log}"
mkdir -p "$(dirname "${out}")"
echo "waiting for the pfSense SSH banner on 172.17.0.1:9922 (reboot pfSense now); output: ${out}"
# A frozen pfSense still accepts TCP in the kernel: only a banner proves sshd serves again.
until timeout 3 bash -c 'exec 3<>/dev/tcp/172.17.0.1/9922 && head -c 8 <&3' 2>/dev/null | grep -q '^SSH-2.0'; do
  sleep 1
done
echo "$(date '+%T') sshd answers: enter the YubiKey PIN and touch the key NOW (window of ~25 s)"
# ControlMaster=auto leaves a master socket so other read-only probes can reuse this session.
ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=40 \
  -o ControlMaster=auto -o ControlPersist=4h -p 9922 admin@172.17.0.1 /bin/sh -s -- "${PFSENSE_CAPTURE_ROUNDS:-180}" \
  < "${here}/freeze-capture-remote.sh" | tee -a "${out}"
echo "$(date '+%T') capture ended; the last '=== ' timestamp in ${out} dates the end of the stream"
