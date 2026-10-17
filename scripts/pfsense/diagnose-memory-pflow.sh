#!/usr/bin/env bash
# Read-only pfSense memory and pflow evidence; no service restarts or secrets.
set -euo pipefail
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
usage() { echo "usage: $0 --check [--target SSH_ALIAS] [--port PORT]" >&2; }
[[ "${1:-}" == "--check" ]] || { usage; exit 2; }
shift
while (($#)); do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || { usage; exit 2; }; port="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
opts=(-o BatchMode=yes -o ConnectTimeout=8)
[[ -z "$port" ]] || opts+=(-p "$port")
echo "Read-only pfSense memory/pflow audit target=$target"
ssh "${opts[@]}" "$target" '/bin/sh -s' <<'REMOTE'
set -u
echo '==> Timestamp and uptime'
date; uptime
echo '==> Memory / swap'
sysctl hw.physmem vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_cache_count vm.stats.vm.v_page_size 2>/dev/null || true
swapinfo -h 2>/dev/null || true
echo '==> Largest resident processes (KiB)'
ps axo pid,rss,pcpu,command | sort -nr -k2 | head -18 || true
echo '==> Unbound health and memory'
unbound-control -c /var/unbound/unbound.conf status 2>&1 || true
unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | grep -E '^(mem[.]|total[.]num[.]queries|total[.]num[.]recursivereplies)' | head -22 || true
echo '==> Recent kernel memory failures (historical evidence; check timestamps)'
dmesg | grep -Ei 'failed to reclaim|out of swap|killed.*(unbound|php|netstat)' | tail -20 || true
echo '==> pflow interfaces and sockets'
ifconfig -l | tr ' ' '\n' | grep '^pflow' || true
sockstat -4 -l 2>/dev/null | grep -Ei 'pflow|2055' || true
echo '==> pflow runtime configuration (redacted: no config.xml dump)'
for iface in $(ifconfig -l | tr ' ' '\n' | grep '^pflow'); do
  ifconfig "$iface" 2>/dev/null | grep -E '(^pflow|pflow:|src |dst |version|domain|status)' || true
done
echo '==> DNS regression smoke'
for name in defectdojo.int.albandrieu.com s3.int.albandrieu.com; do
  drill "$name" @127.0.0.1 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -4 || true
done
REMOTE
