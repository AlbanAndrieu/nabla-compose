#!/usr/bin/env bash
# Read-only pflow activation preflight. Never loads a kernel module or changes PF rules.
set -euo pipefail
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
case "${1:---check}" in --check) ;; *) echo 'Usage: diagnose-pflow-activation.sh --check' >&2; exit 2;; esac
ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" '/bin/sh -s' <<'REMOTE'
set -u
echo '=== Current clock, memory and OOM ==='
date; uptime
sysctl -n vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null | awk 'NR==1{f=$1} NR==2{i=$1} NR==3{printf "free+inactive: %.1f MiB\n",(f+i)*$1/1048576}'
echo '=== pfBlockerNG scheduled work ==='
ps axo pid,command | grep '[p]fblockerng.php cron' || true
echo '=== pflow module and export configuration ==='
kldstat | grep -i pflow || true
pflowctl -l 2>&1 || true
ifconfig -l | tr ' ' '\n' | grep '^pflow' || true
echo '=== pfSense pflow integration: source line numbers (no config values) ==='
grep -nE 'pflowctl|pflow_create|pflow_export' /etc/inc/filter.inc 2>/dev/null | cut -c1-180 | head -35 || true
echo '=== DNS status ==='
unbound-control -c /var/unbound/unbound.conf status 2>&1 | head -10 || true
drill defectdojo.int.albandrieu.com @127.0.0.1 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -4 || true
REMOTE
