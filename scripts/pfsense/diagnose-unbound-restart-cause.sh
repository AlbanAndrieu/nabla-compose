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
echo '=== Service Watchdog membership (read-only configuration, names only) ==='
if [ -r /conf/config.xml ]; then
  awk '
    /<servicewatchdog>/ {inside=1; found=1}
    inside && /<name>[[:space:]]*unbound[[:space:]]*<\/name>/ {watched=1}
    /<\/servicewatchdog>/ {inside=0}
    END {
      if(watched) print "watchdog_unbound_membership=LISTED"
      else if(found) print "watchdog_unbound_membership=NOT_LISTED"
      else print "watchdog_unbound_membership=PACKAGE_SECTION_NOT_OBSERVED"
    }
  ' /conf/config.xml
else
  echo 'watchdog_unbound_membership=CONFIG_UNAVAILABLE'
fi
echo '=== Installed pfBlockerNG version and apply implementation (not execution) ==='
if command -v pkg >/dev/null 2>&1; then
  found_package=no
  for name in pfSense-pkg-pfBlockerNG-devel pfSense-pkg-pfBlockerNG; do
    version=$(pkg query '%v' "$name" 2>/dev/null | head -1 || true)
    case "$version" in
      ''|*[!A-Za-z0-9._,+~-]*) ;;
      *) printf 'pfblocker_package=%s version=%s\n' "$name" "$version"
         found_package=yes ;;
    esac
  done
  [ "$found_package" = yes ] || echo 'pfblocker_package=NOT_OBSERVED'
else
  echo 'pfblocker_package=PKG_UNAVAILABLE'
fi
implementation_seen=no
for file in /usr/local/pkg/pfblockerng/pfblockerng.inc \
            /usr/local/pkg/pfblockerng.inc; do
  [ -r "$file" ] || continue
  implementation_seen=yes
  for fn in pfb_stop_start_unbound pfb_reload_unbound pfb_validate_unbound; do
    if grep -Eq "function[[:space:]]+$fn[[:space:]]*[(]" "$file" 2>/dev/null; then
      printf 'pfblocker_implementation_function=%s present=yes\n' "$fn"
    fi
  done
  # Static source call sites only; no PHP executed, no source lines printed.
  # The containing function is a best-effort clue, never runtime attribution.
  awk '
    /^[[:space:]]*(function|public[[:space:]]+function)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*[(]/ {
      name=$0
      sub(/^.*function[[:space:]]+/, "", name)
      sub(/[[:space:]]*[(].*$/, "", name)
      caller=name
    }
    /^[[:space:]]*(\/\/|#|\*|\/\*)/ {next}
    /pfb_stop_start_unbound[[:space:]]*[(]/ && $0 !~ /function[[:space:]]+pfb_stop_start_unbound/ {
      calls["pfb_stop_start_unbound" SUBSEP caller]++
    }
    /pfb_reload_unbound[[:space:]]*[(]/ && $0 !~ /function[[:space:]]+pfb_reload_unbound/ {
      calls["pfb_reload_unbound" SUBSEP caller]++
    }
    END {
      for (pair in calls) {
        split(pair, components, SUBSEP)
        target=components[1]; location=components[2]
        if(location !~ /^[A-Za-z_][A-Za-z0-9_]*$/) location="unknown"
        printf "pfblocker_possible_call_target=%s enclosing_function=%s sites=%d\n",
          target,location,calls[pair]
      }
    }
  ' "$file" | sort | head -20
  echo 'pfblocker_possible_call_sites_are_execution_proof=no'
  break
done
[ "$implementation_seen" = yes ] ||
  echo 'pfblocker_implementation=NOT_OBSERVED'
echo 'pfblocker_implementation_is_execution_proof=no'
echo '=== Bounded lifecycle and kernel signals (raw messages withheld) ==='
for file in /var/log/system.log /var/log/system.log.0 /var/log/system.log.1 \
            /var/log/resolver.log /var/log/resolver.log.0 \
            /var/log/cron.log /var/log/cron.log.0 \
            /var/log/configd.log /var/log/configd.log.0 \
            /var/log/pfblockerng/pfblockerng.log /var/log/pfblockerng/pfblockerng.log.0; do
  [ -r "$file" ] || continue
  case "$file" in
    *system*) source=system ;;
    *resolver*) source=resolver ;;
    *cron*) source=cron ;;
    *configd*) source=configd ;;
    *) source=pfblockerng ;;
  esac
  printf '=== %s lifecycle events (bounded, redacted) ===\n' "$source"
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
    function pfblocker_time_marker(line, v) {
      # Log timestamps are intermittent [ NOW ] expansions, not per-line.
      # Preserve the nearest prior marker only as contextual evidence.
      if(match(line, /\\[[[:space:]]*[0-9][0-9]\\/[0-9][0-9]\\/[0-9][0-9] [0-9][0-9]?:[0-9][0-9]:[0-9][0-9][[:space:]]*\\]/)) {
        v=substr(line,RSTART,RLENGTH)
        gsub(/\\[|\\]/,"",v)
        sub(/^[[:space:]]*/,"",v)
        sub(/[[:space:]]*$/,"",v)
        return v
      }
      return ""
    }
    {
      event=""
      marker=""
      if(source=="pfblockerng") {
        marker=pfblocker_time_marker($0)
        if(marker!="") {last_header_time=marker;last_header_line=NR}
      }
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
      } else if(source=="configd") {
        if($0 ~ /[Uu]nbound/ &&
           $0 ~ /[Rr]estart|[Rr]eload|[Ss]top|[Ss]tart/)
          event="configd_unbound_action"
      } else if(source=="pfblockerng") {
        if($0 ~ /Stopping Unbound Resolver|Stopping Unbound Service/)
          event="pfblocker_unbound_stop_marker"
        else if($0 ~ /Starting Unbound Resolver|Starting Unbound Service/)
          event="pfblocker_unbound_start_marker"
        else if($0 ~ /Restarting Unbound Resolver|Restarting Unbound[[:space:]]/)
          event="pfblocker_unbound_restart_marker"
        else if($0 ~ /Restarting DNSBL Service/) event="dnsbl_service_restart_marker"
        else if($0 ~ /UPDATE PROCESS ENDED/) event="pfblockerng_update_end"
        else if($0 ~ /DNSBL.*(PASSED|FAILED)/) event="dnsbl_update_result"
      }
      if(event!="") {
        level=(event=="kernel_oom_unbound" || event=="unbound_bind_conflict" ||
               event=="watchdog_unbound_restart" ? "WARN: " : "")
        printf "%ssignal_source=%s event=%s timestamp=%s",
          level,source,event,stamp($0)
        # Do not misrepresent a block's header as the event's own timestamp.
        if(source=="pfblockerng" && last_header_time!="" &&
           (NR-last_header_line)<=80) {
          printf " preceding_header_local=%s header_gap_lines=%d",
            last_header_time,NR-last_header_line
        }
        printf "\n"
      }
    }
  ' | tail -35 || true
done
echo '=== Memory context (sample only, not a nocturnal measurement) ==='
sysctl vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null || true
echo '=== Evidence interpretation ==='
echo 'kernel_oom_unbound=CONFIRMED_KERNEL_KILL_WHEN_TIMESTAMP_MATCHES'
echo 'dnsbl_python_exit=MODULE_SHUTDOWN_NOT_PROOF_OF_CALLER'
echo 'dnsbl_service_restart_marker=DNSBL_ACTION_NOT_PROOF_OF_UNBOUND_PID_CHANGE'
echo 'pfblocker_unbound_stop_marker=SOURCE_REPORTS_A_STOP_REQUEST_NOT_PID_VERIFIED'
echo 'pfblocker_unbound_start_marker=SOURCE_REPORTS_A_START_REQUEST_NOT_READINESS_PROOF'
echo 'unbound_bind_conflict=OVERLAPPING_SOCKET_ATTEMPTS_OR_STALE_LISTENER'
echo 'cron_schedule=NOT_PROOF_OF_EXECUTION'
echo 'watchdog_membership=SEE_READ_ONLY_CONFIG_PROBE'
echo 'restart_initiator=NOT_PROVEN_UNLESS_EXPLICIT_LIFECYCLE_ACTION'
echo '=== End of read-only Unbound restart triage ==='
REMOTE
