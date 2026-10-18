#!/usr/bin/env bash
# Read-only FreeBSD/pfSense memory-pressure sampler. Runs from workstation.
set -euo pipefail
target="home.albandrieu.com"
samples=10
interval=30
while (($#)); do
  case "$1" in
    --check) shift ;;
    --target) target="${2:?missing SSH target}"; shift 2 ;;
    --samples) samples="${2:?missing samples}"; shift 2 ;;
    --interval) interval="${2:?missing interval}"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--check] [--target SSH_ALIAS] [--samples N] [--interval SECONDS]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$samples" =~ ^[0-9]+$ && "$samples" -gt 0 && "$samples" -le 120 ]] || { echo 'samples must be 1..120' >&2; exit 2; }
[[ "$interval" =~ ^[0-9]+$ && "$interval" -le 3600 ]] || { echo 'interval must be 0..3600 seconds' >&2; exit 2; }
ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" /bin/sh -s -- "$samples" "$interval" <<'REMOTE'
samples="$1"; interval="$2"; n=0
echo 'timestamp,available_mib,free_mib,inactive_mib,wired_mib,active_mib,unbound_pid,unbound_rss_kib,pfblocker_cron_count,php_fpm_rss_kib'
while [ "$n" -lt "$samples" ]; do
  stamp=$(date '+%Y-%m-%dT%H:%M:%S%z')
  vals=$(sysctl -n vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_wire_count vm.stats.vm.v_active_count vm.stats.vm.v_page_size 2>/dev/null) || exit 1
  set -- $vals
  free="$1"; inactive="$2"; wired="$3"; active="$4"; pagesize="$5"
  proc=$(ps axo pid,rss,command 2>/dev/null)
  unbound=$(printf '%s\n' "$proc" | awk '/[u]nbound -c \/var\/unbound\/unbound.conf/ {print $1 "," $2; exit}')
  cron=$(printf '%s\n' "$proc" | awk '/[p]fblockerng.php cron/ {n++} END {print n+0}')
  fpm=$(printf '%s\n' "$proc" | awk '/php-fpm: pool nginx/ {s+=$2} END {print s+0}')
  awk -v t="$stamp" -v f="$free" -v i="$inactive" -v w="$wired" -v a="$active" -v p="$pagesize" -v u="$unbound" -v c="$cron" -v h="$fpm" 'BEGIN {
    split(u, x, ","); printf "%s,%.1f,%.1f,%.1f,%.1f,%.1f,%s,%s,%s,%s\n", t,(f+i)*p/1048576,f*p/1048576,i*p/1048576,w*p/1048576,a*p/1048576,x[1],x[2],c,h
  }'
  n=$((n+1))
  [ "$n" -lt "$samples" ] && sleep "$interval"
done
REMOTE
