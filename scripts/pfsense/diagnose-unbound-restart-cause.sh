#!/usr/bin/env bash
# Netgate 1100: classify Unbound restart evidence without modifying pfSense.
# Workstation only. No service restarts, reloads, credentials or raw logs.
set -euo pipefail
# shellcheck source=scripts/pfsense/console.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/console.sh"
usage() { printf 'Usage: %s --check [--target SSH_ALIAS] [--port SSH_PORT]\n' "$0"; }
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; exit 0; fi
if [[ "${1:-}" != "--check" ]]; then usage >&2; exit 2; fi
shift
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
while (($#)); do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "$target" =~ ^[A-Za-z0-9._@-]+$ ]] || { echo 'Invalid SSH target' >&2; exit 2; }
if [[ -n "$port" ]]; then
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port >= 1 && 10#$port <= 65535)) ||
    { echo 'Invalid SSH port' >&2; exit 2; }
fi
args=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)
[[ -z "$port" ]] || args+=(-p "$port")
pfsense_ui_banner "Unbound restart provenance · read-only"
ssh "${args[@]}" "$target" '/bin/sh -s' <<'REMOTE' | pfsense_ui_render
set -u
# Only fixed categories are sent to the workstation. Preserve offsets at DST.
echo '=== Current Unbound identity (not restart cause) ==='
date '+pfSense_time=%Y-%m-%dT%H:%M:%S%z'
ps axo pid,lstart,rss,comm 2>/dev/null | awk '
  NR > 1 && $1 ~ /^[0-9]+$/ && $NF == "unbound" {
    printf "unbound_pid=%s started_local=%s_%s_%s_%s_%s rss_kib=%s\n",
      $1,$2,$3,$4,$5,$6,$7
  }
' | head -3 || true
if unbound-control -c /var/unbound/unbound.conf status >/dev/null 2>&1; then
  echo 'unbound_control=REACHABLE'
else
  echo 'unbound_control=UNVERIFIED'
fi
echo '=== Configured task schedules (not proof of execution) ==='
if [ -r /etc/crontab ]; then
  awk '
    /^[[:space:]]*#/ || NF < 7 {next}
    {
      type=""
      for (i=7; i<=NF; i++) {
        if ($i ~ /snort_check_for_rule_updates/) type="snort_update"
        else if ($i ~ /pfblockerng[.]php/) type="pfblockerng"
        else if ($i ~ /servicewatchdog_cron/) type="servicewatchdog"
      }
      if(type!="") printf "scheduled_task=%s minute=%s hour=%s\n", type,$1,$2
    }
  ' /etc/crontab | head -20
fi
echo '=== Bounded lifecycle and kernel signals (raw messages withheld) ==='
for file in /var/log/system.log /var/log/system.log.0 /var/log/system.log.1 \
            /var/log/resolver.log /var/log/resolver.log.0 \
            /var/log/cron.log /var/log/cron.log.0 \
            /var/log/pfblockerng/pfblockerng.log /var/log/pfblockerng/pfblockerng.log.0; do
  [ -r "$file" ] || continue
  case "$file" in
    *system*) source=system ;;
    *resolver*) source=resolver ;;
    *cron*) source=cron ;;
    *) source=pfblockerng ;;
  esac
  printf 'log_family=%s readable=yes\n' "$source"
  tail -n 4000 "$file" | awk -v source="$source" '
    function stamp(line, s) {
      s=line
      sub(/^<[0-9]+>[0-9]+[[:space:]]+/, "", s)
      if(match(s,/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9](\.[0-9]+)?([+-][0-9][0-9]:[0-9][0-9]|Z)?/))
        return substr(s,RSTART,RLENGTH)
      if(match(s,/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/))
        return substr(s,RSTART,RLENGTH)
      if(match(s,/^[0-9][0-9]\/[0-9][0-9]\/[0-9][0-9][0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/))
        return substr(s,RSTART,RLENGTH)
      if(match(s,/^[A-Z][a-z][a-z] [ 0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/))
        return substr(s,RSTART,RLENGTH)
      return "unknown"
    }
    {
      event=""
      if(source=="system" || source=="resolver") {
        if($0 ~ /failed to reclaim memory|out of swap|waited too long to allocate a page/)
          event=($0 ~ /[(]unbound[)]/ ? "kernel_oom_unbound" : "kernel_oom_other")
        else if($0 ~ /pfb_unbound[.]py script exiting/) event="dnsbl_python_exit"
        else if($0 ~ /Restart of unbound/) event="unbound_restart_notice"
        else if($0 ~ /bind: address already in use|fatal error: could not open ports/)
          event="unbound_bind_conflict"
        else if($0 ~ /[Ww]atchdog/ && $0 ~ /[Uu]nbound/ && $0 ~ /[Rr]estart/)
          event="watchdog_unbound_restart"
        else if($0 ~ /[Cc]onfigd/ && $0 ~ /[Uu]nbound/ && $0 ~ /[Rr]estart|[Rr]eload/)
          event="configd_unbound_action"
      } else if(source=="cron") {
        if($0 ~ /snort_check_for_rule_updates/) event="snort_cron_exec"
        else if($0 ~ /pfblockerng[.]php/) event="pfblockerng_cron_exec"
        else if($0 ~ /servicewatchdog_cron/) event="watchdog_cron_exec"
      } else if(source=="pfblockerng") {
        if($0 ~ /Restarting DNSBL Service/) event="dnsbl_service_restart_marker"
        else if($0 ~ /UPDATE PROCESS ENDED/) event="pfblockerng_update_end"
        else if($0 ~ /DNSBL.*(PASSED|FAILED)/) event="dnsbl_update_result"
      }
      if(event!="")
        printf "signal_source=%s event=%s timestamp=%s\n",source,event,stamp($0)
    }
  ' | tail -35 || true
done
echo '=== Memory context (sample only, not a nocturnal measurement) ==='
sysctl vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null || true
echo '=== Evidence interpretation ==='
echo 'kernel_oom_unbound=CONFIRMED_KERNEL_KILL_WHEN_TIMESTAMP_MATCHES'
echo 'dnsbl_python_exit=MODULE_SHUTDOWN_NOT_PROOF_OF_CALLER'
echo 'dnsbl_service_restart_marker=DNSBL_ACTION_NOT_PROOF_OF_UNBOUND_PID_CHANGE'
echo 'unbound_bind_conflict=OVERLAPPING_SOCKET_ATTEMPTS_OR_STALE_LISTENER'
echo 'cron_schedule=NOT_PROOF_OF_EXECUTION'
echo 'watchdog_membership=NOT_VERIFIED'
echo 'restart_initiator=NOT_PROVEN_UNLESS_EXPLICIT_LIFECYCLE_ACTION'
echo '=== End of read-only Unbound restart triage ==='
REMOTE
