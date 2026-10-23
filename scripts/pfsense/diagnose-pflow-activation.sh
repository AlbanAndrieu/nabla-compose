#!/usr/bin/env bash
# Read-only pfSense pflow/Unbound health and optional bounded packet capture.
# Does not load modules, change PF rules, or restart services.
set -euo pipefail
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
capture=false
while (($#)); do
  case "$1" in
    --check) shift ;;
    --capture) capture=true; shift ;;
    -h|--help) echo "Usage: $0 [--check] [--capture]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
args=(-o BatchMode=yes -o ConnectTimeout=10)
[[ -z "$port" ]] || args+=(-p "$port")
ssh "${args[@]}" "$target" '/bin/sh -s' -- "$capture" <<'REMOTE'
set -u
capture="$1"
echo '=== Clock and uptime ==='
date; uptime
echo '=== FreeBSD memory: free + inactive (MiB) ==='
sysctl -n vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null |
  awk 'NR==1{f=$1} NR==2{i=$1} NR==3{printf "%.1f MiB\n",(f+i)*$1/1048576}'
echo '=== pflow module and exporter ==='
if kldstat 2>/dev/null | grep -i 'pflow[.]ko'; then
  pflowctl -l 2>&1 || true
else
  echo 'NOT ACTIVE: pflow.ko not loaded (check Save AND Apply in firewall_pflow.php)'
fi
echo '=== pflow interfaces ==='
ifconfig -l | tr ' ' '\n' | grep '^pflow' || true
echo '=== pfBlockerNG cron and memory-consuming services ==='
ps axo pid,rss,command | grep -E '[p]fblockerng.php cron|[p]hp_pfb|[u]nbound -c' | head -15 || true
echo '=== Unbound status and DNS smoke ==='
unbound-control -c /var/unbound/unbound.conf status 2>&1 | head -10 || true
drill defectdojo.int.albandrieu.com @127.0.0.1 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -4 || true
echo '=== Recent kernel OOM evidence (log timestamps) ==='
grep 'failed to reclaim memory' /var/log/system.log 2>/dev/null | tail -8 || true
echo '=== pfSense pflow native integration ==='
grep -nE '^function filter_pflow_(exporters_clear|exporter_configure_all|exporter_configure)\(' /etc/inc/filter.inc 2>/dev/null || true
if [ "$capture" = true ]; then
  echo '=== Bounded 30s pfSense LAN capture: NetFlow v5 UDP/2055 ==='
  echo 'NOTE: tcpdump packets received by filter is NOT the count of matched/exported packets; use packets captured.'
  if command -v timeout >/dev/null 2>&1; then
    timeout 30 tcpdump -n -i mvneta0.4091 -c 10 'udp and src host 172.17.0.1 and dst host 172.17.0.24 and dst port 2055' 2>&1 || true
  else
    echo 'SKIP: timeout command unavailable; do not run unbounded capture automatically'
  fi
  echo 'Interpret packets captured: >0 confirms pfSense sent NetFlow UDP; 0 means none observed in this capture window.'
  echo 'New PF states matching a tracked rule are needed before flow export; collector receipt remains unverified.'
fi
REMOTE
