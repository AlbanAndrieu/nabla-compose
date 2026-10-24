#!/usr/bin/env bash
# Read-only pfSense/FreeBSD Unbound crash and memory incident evidence.
# Execute from a workstation with SSH access. No restart, configuration write or secrets.
set -euo pipefail
# Workstation presentation; remote shell never sources workstation helpers.
# shellcheck source=scripts/pfsense/console.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/console.sh"
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
case "${1:---check}" in --check) ;; *) echo "Usage: $0 --check" >&2; exit 2;; esac
args=(-o BatchMode=yes -o ConnectTimeout=10)
[[ -z "${port}" ]] || args+=(-p "${port}")
pfsense_ui_banner "unbound crash memory · read-only"
ssh "${args[@]}" "${target}" '/bin/sh -s' <<'REMOTE' | pfsense_ui_render
set -u
echo '=== UTC/local time, uptime, Unbound identity ==='
date; uptime
ps axo pid,lstart,rss,pcpu,command | grep '[u]nbound -c /var/unbound/unbound.conf' | head -4
unbound-control -c /var/unbound/unbound.conf status 2>&1 | head -12 || true
echo '=== FreeBSD memory (sample, not proof of available allocation headroom) ==='
sysctl hw.physmem vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_wire_count vm.stats.vm.v_active_count vm.stats.vm.v_page_size 2>/dev/null || true
swapinfo -h 2>/dev/null || true
vmstat -z 2>/dev/null | head -18 || true
echo '=== Memory-heavy processes (RSS includes shared pages; not additive) ==='
ps axo pid,rss,pcpu,command | sort -nr -k2 | head -22
echo '=== Kernel OOM evidence with timestamps where available ==='
dmesg -a 2>/dev/null | grep -Ei 'failed to reclaim|out of swap|killed.*(unbound|php|netstat)|memory allocation failure' | tail -35 || true
echo '=== Rotated system logs: selected crash evidence only ==='
for f in /var/log/system.log /var/log/system.log.0 /var/log/system.log.1 /var/log/resolver.log /var/log/resolver.log.0; do
  [ -f "$f" ] || continue
  echo "log file: $f"
  grep -Ei 'unbound.*(exit|stop|restart|start|signal|killed|fatal|error|crash)|failed to reclaim|out of swap|oom' "$f" 2>/dev/null | tail -18 || true
done
echo '=== Unbound query stats (no reset) ==='
unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | grep -E '^(total.num.queries=|total.num.queries_timed_out=|total.num.queries_discard_timeout=|mem[.]|thread[0-9]+.num.queries=)' | head -25 || true
echo '=== Cron pressure and safe DNS smoke ==='
ps axo pid,rss,command | grep -E '[p]fblockerng.php cron|[p]hp_pfb|[u]nbound -c' | head -12 || true
for host in defectdojo.int.albandrieu.com s3.int.albandrieu.com; do
  drill "$host" @127.0.0.1 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -4 || true
done
echo '=== pfBlockerNG update log (native format is not ISO 8601) ==='
if [ -f /var/log/pfblockerng/pfblockerng.log ]; then
  grep -E 'UPDATE PROCESS ENDED|Saving configuration|Restarting DNSBL Service|Starting firewall filter daemon' /var/log/pfblockerng/pfblockerng.log 2>/dev/null | tail -18 || true
fi
echo '=== Unbound / WireGuard ACL changes and restart failures ==='
for f in /var/log/system.log /var/log/system.log.0 /var/log/resolver.log; do
  [ -f "$f" ] || continue
  grep -Ei 'WireGuard.*Unbound ACL|could not open ports|address already in use|Restart of unbound' "$f" 2>/dev/null | tail -12 || true
done
echo '=== pflow kernel module and exporter (read-only correlation) ==='
if kldstat 2>/dev/null | grep -i 'pflow[.]ko'; then
  pflowctl -l 2>&1 || true
else
  echo 'pflow.ko not loaded'
fi
REMOTE
