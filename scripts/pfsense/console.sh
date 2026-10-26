#!/usr/bin/env bash
# Workstation-only UI. The pfSense /bin/sh collector remains unchanged.
# TTY=compact colored; pipes, CI and PFSENSE_OUTPUT=raw are byte-identical.
pfsense_ui_active() {
  case "${PFSENSE_OUTPUT:-auto}" in
    raw) return 1 ;;
    compact|verbose) return 0 ;;
    auto) [[ -t 1 && -z "${CI:-}" ]] ;;
    *) return 1 ;;
  esac
}
pfsense_ui_color() {
  [[ -z "${NO_COLOR:-}" && "${TERM:-}" != dumb && "${PFSENSE_COLOR:-auto}" != never ]] || return 1
  [[ "${PFSENSE_COLOR:-auto}" == always ]] || [[ -t 1 && -z "${CI:-}" ]]
}
pfsense_ui_banner() {
  pfsense_ui_active || return 0
  local on='' off=''
  if pfsense_ui_color; then on=$'\033[1;36m'; off=$'\033[0m'; fi
  printf '%s🛡️ pfSense · %s%s\n' "$on" "$*" "$off"
}
pfsense_ui_render() {
  if ! pfsense_ui_active; then cat; return; fi
  local mode="${PFSENSE_OUTPUT:-auto}" c='' g='' y='' r='' z='' d=''
  [[ "$mode" != auto ]] || mode=compact
  if pfsense_ui_color; then
    c=$'\033[1;36m'; g=$'\033[32m'; y=$'\033[33m'
    r=$'\033[31m'; d=$'\033[2m'; z=$'\033[0m'
  fi
  LC_ALL=C awk -v mode="$mode" -v cyan="$c" -v green="$g" -v yellow="$y" \
    -v red="$r" -v dim="$d" -v reset="$z" '
    function flush( i, bucket) {
      # Collapse historical OOM kills by minute in compact mode.
      if(mode=="compact") {
        for(i=1;i<=pending_count;i++) {
          bucket=pending_order[i]
          summary="Historical OOM minute="bucket" · kernel kills="pending[bucket]
          if(pending_unbound[bucket]>0) summary=summary" · unbound kills="pending_unbound[bucket]
          emit(summary,"warn",1)
          delete pending_unbound[bucket]
          delete pending[bucket]
          delete pending_order[i]
        }
        pending_count=0
      }
      if(hidden) {printf "%s  ... %d lines omitted (PFSENSE_OUTPUT=verbose)%s\n",dim,hidden,reset;total_hidden+=hidden}
      hidden=0;visible=0
    }
    function emit(s, level, priority, col, icon) {
      if(mode=="compact" && visible>=14 && !priority) {hidden++;return}
      visible++;col="";icon=""
      if(level=="warn") {warnings++;col=yellow;icon="⚠️ "}
      if(level=="error") {errors++;col=red;icon="❌ "}
      if(level=="ok") {col=green;icon="✅ "}
      printf "%s%s%s%s\n",col,icon,s,reset
    }
    function logstamp(s) {
      sub(/^<[0-9]+>[0-9]+[[:space:]]+/,"",s)
      if(match(s,/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9](\.[0-9]+)?([+-][0-9][0-9]:[0-9][0-9]|Z)?/)) return substr(s,RSTART,RLENGTH)
      return "unknown"
    }

    # The same kernel kill is printed by both the chronology and resolver logs.
    # Deduplicate by complete event timestamp, not minute, PID or service name.
    function oom_minute(ts, minute) {
      if(ts=="unknown") return "unknown"
      minute=substr(ts,1,16)
      # DST fallback produces two distinct 02:10 minutes: keep UTC offsets.
      if(ts ~ /[+-][0-9][0-9]:[0-9][0-9]$/)
        return minute" "substr(ts,length(ts)-5,6)
      if(ts ~ /Z$/) return minute" Z"
      return minute" (offset unknown)"
    }
    function historic_oom(ts, victim, id, minute, message) {
      id=(ts=="unknown" ? "unknown-" ++unknown_id : ts)
      if(seen_oom[id]++) {oom_duplicates++; return}
      oom_unique++
      minute=oom_minute(ts)
      if(ts!="unknown" && !seen_minute[minute]++) oom_minutes++
      if(mode=="compact") {
        if(!(minute in pending)) {pending_order[++pending_count]=minute;pending[minute]=0}
        pending[minute]++
        if(victim=="unbound") pending_unbound[minute]++
      } else {
        message="Historical kernel OOM"
        if(victim!="") message=message" victim="victim
        emit(message" timestamp="ts,"warn",1)
      }
    }
    function syslog_kind(line) {
      if(line ~ /address already in use|could not open ports/) return "unbound_bind_conflict"
      if(line ~ /Restart of unbound/) return "unbound_restart_notice"
      if(line ~ /pfb_unbound[.]py script exiting/) return "dnsbl_python_exit"
      if(line ~ /failed to prime trust anchor/) return "dnssec_trust_anchor_failure"
      if(line ~ /so-sndbuf|No buffer space available/) return "socket_buffer_warning"
      if(line ~ /[Cc]rowd[Ss]ec/ && line ~ /[Ss]tart|[Rr]estart|[Ss]top/) return "crowdsec_lifecycle_log"
      return "other_resolver_event"
    }
    /^timestamp,available_mib,free_mib,/ {csv=1;flush();sections++;printf "\n%s📊 Memory samples · MiB/KiB%s\n",cyan,reset;next}
    csv {
      n=split($0,a,",")
      if(n>=10) {emit(a[1]" · available="a[2]" MiB · unbound="a[8]" KiB · PHP-FPM="a[10]" KiB","",1);next}
    }
    /^(=== |==> )/ {
      flush();sections++;name=$0;sub(/^=== /,"",name);sub(/^==> /,"",name);sub(/ ===$/,"",name)
      printf "\n%s🔎 %s%s\n",cyan,name,reset;next
    }
    /^sampler_budget=samples=/ {
      sampler_run=1
      split($1,v,"=")
      sampler_expected=v[3]+0
      emit($0,"",1);next
    }
    /^sample_seq=[0-9]+ timestamp=/ {
      sampler_run=1
      available=""
      timestamp=""
      for(j=1;j<=NF;j++) {
        split($j,v,"=")
        if(v[1]=="available_kib" && v[2] ~ /^[0-9]+$/) available=v[2]+0
        if(v[1]=="timestamp") timestamp=v[2]
      }
      if(available=="") {
        collector_failed=1
        emit("ERROR: sampler_missing_available_kib","error",1)
      } else {
        sampler_samples++
        if(sampler_samples==1 || available<sampler_min) {sampler_min=available;sampler_min_ts=timestamp}
        if(sampler_samples==1 || available>sampler_max) {sampler_max=available;sampler_max_ts=timestamp}
        if(available<131072) sampler_below_128++
        if(available<65536) sampler_below_64++
      }
      emit($0,"",1);next
    }
    /^source=snort .*timestamp=unknown$/ && mode=="compact" {snort_unknown++;next}
    # Dedicated restart-provenance collector uses a typed OOM signal.
    # Count this as historical evidence, not a current down service.
    /^(WARN: )?signal_source=system event=kernel_oom_(unbound|other) timestamp=/ {
      ts=$0;sub(/^.*timestamp=/,"",ts)
      victim=($0 ~ /event=kernel_oom_unbound / ? "unbound" : "other")
      historic_oom(ts,victim);next
    }
    /^source=system event=kernel_oom/ {
      ts=$0;sub(/^.*timestamp=/,"",ts)
      historic_oom(ts);next
    }
    /^<[0-9]+>[0-9]+ / && /failed to reclaim memory|out of swap/ {
      historic_oom(logstamp($0));next
    }
    /^<[0-9]+>[0-9]+ / {
      kind=syslog_kind($0)
      if(kind=="other_resolver_event" && mode=="compact") {uncategorized++;next}
      emit("resolver_event="kind" timestamp="logstamp($0)" (contents suppressed)",
        (kind=="unbound_bind_conflict" || kind=="dnssec_trust_anchor_failure" ? "warn" : ""),0)
      next
    }
    # Current process start time is observable; the restart cause is not.
    /^[[:space:]]*[0-9]+[[:space:]]+[A-Z][a-z][a-z][[:space:]]+[A-Z][a-z][a-z][[:space:]]+[ 0-9][0-9][[:space:]]/ && /unbound -c \/var\/unbound\/unbound[.]conf/ {
      if($7 ~ /^[0-9]+$/ && $1 ~ /^[0-9]+$/) {
        emit("Unbound process pid="$1" started="$3" "$4" "$5" rss_kib="$7" · restart cause UNKNOWN","",1)
        next
      }
    }
    /^(vm[.]stats[.]vm[.]v_(free_count|inactive_count|page_size):)/ {
      if($1=="vm.stats.vm.v_free_count:") free_pages=$2
      if($1=="vm.stats.vm.v_inactive_count:") inactive_pages=$2
      if($1=="vm.stats.vm.v_page_size:") page_bytes=$2
      emit($0,"",0)
      if(free_pages ~ /^[0-9]+$/ && inactive_pages ~ /^[0-9]+$/ && page_bytes ~ /^[0-9]+$/ &&
         page_bytes>0 && !shown_memory++) {
        printf "%s📊 Free + inactive ≈ %.1f MiB (snapshot; not nocturnal headroom)%s\n",
          cyan,(free_pages+inactive_pages)*page_bytes/1048576,reset
      }
      next
    }
    /^ERROR: (lifecycle_classifier_failed|feed_log_classifier_failed|sampler_[A-Za-z0-9_]+)/ {
      collector_failed=1; emit($0,"error",1);next
    }
    /^(ERROR:|FAIL:|FAIL |BLOCKED:|.*status=BLOCKED)/ {emit($0,"error",1);next}
    /^(WARN(ING)?:|WARN |NOT ACTIVE:|.*status=unknown|.*=NOT_VERIFIED|.*transport=unavailable)/ {emit($0,"warn",1);next}
    /^(PASS:|PASS |OK:)/ {emit($0,"ok",0);next}
    {s=$0;if(mode=="compact" && length(s)>220)s=substr(s,1,217)"...";emit(s,"",0)}
    END {
      flush()
      if(snort_unknown)printf "%s⚠️ Snort: %d events with unknown timestamps%s\n",yellow,snort_unknown,reset
      if(sampler_run && sampler_samples>0) {
        printf "\n%s📊 Memory window · %d %s · available min=%.1f MiB (%s) · max=%.1f MiB (%s) · below 128 MiB=%d · below 64 MiB=%d%s\n",
          cyan,sampler_samples,(sampler_samples==1?"sample":"samples"),sampler_min/1024,sampler_min_ts,sampler_max/1024,sampler_max_ts,
          sampler_below_128,sampler_below_64,reset
      }
      if(collector_failed || sections==0 || (sampler_run && sampler_expected!=sampler_samples)) {
        printf "\n%s❌ EVIDENCE INCOMPLETE · collector failed or missing samples/sections; OOM totals are NOT reliable%s\n",red,reset
      } else if(sampler_run) {
        printf "%sℹ️ Historical OOM events NOT_EVALUATED · this sampler does not inspect kernel logs%s\n",dim,reset
      } else {
        printf "\n%s📊 Evidence only · %d sections · %d distinct historical OOM records · %d duplicate lines suppressed · %d OOM minutes · %d warnings · %d lines omitted%s\n",dim,sections,oom_unique,oom_duplicates,oom_minutes,warnings,total_hidden,reset
      }
      if(uncategorized && mode=="compact") printf "%sℹ️ %d unclassified syslog lines hidden in compact mode%s\n",dim,uncategorized,reset
      if(errors)printf "%s❌ %d explicit error signals to review; not a service health assertion%s\n",red,errors,reset
    }
  '
}
