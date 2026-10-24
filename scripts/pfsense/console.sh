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
    function flush() {
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
    /^timestamp,available_mib,free_mib,/ {csv=1;flush();sections++;printf "\n%s📊 Memory samples · MiB/KiB%s\n",cyan,reset;next}
    csv {
      n=split($0,a,",")
      if(n>=10) {emit(a[1]" · available="a[2]" MiB · unbound="a[8]" KiB · PHP-FPM="a[10]" KiB","",1);next}
    }
    /^(=== |==> )/ {
      flush();sections++;name=$0;sub(/^=== /,"",name);sub(/^==> /,"",name);sub(/ ===$/,"",name)
      printf "\n%s🔎 %s%s\n",cyan,name,reset;next
    }
    /^source=snort .*timestamp=unknown$/ && mode=="compact" {snort_unknown++;next}
    /^source=system event=kernel_oom/ {oom++;emit($0,"error",1);next}
    /^<[0-9]+>[0-9]+ / && /failed to reclaim memory|out of swap/ {
      oom++;emit("kernel OOM timestamp="logstamp($0)" (raw message omitted)","error",1);next
    }
    /^<[0-9]+>[0-9]+ / {emit("syslog timestamp="logstamp($0)" (raw message omitted)","",0);next}
    /^(WARN(ING)?:|WARN |ERROR:|FAIL:|BLOCKED:|NOT ACTIVE:|.*status=unknown|.*=NOT_VERIFIED)/ {emit($0,"warn",1);next}
    /^(PASS:|PASS |OK:)/ {emit($0,"ok",0);next}
    {s=$0;if(mode=="compact" && length(s)>220)s=substr(s,1,217)"...";emit(s,"",0)}
    END {
      flush()
      if(snort_unknown)printf "%s⚠️ Snort: %d events with unknown timestamps%s\n",yellow,snort_unknown,reset
      printf "\n%s📊 Evidence only · %d sections · %d OOM mentions · %d warnings · %d lines omitted%s\n",dim,sections,oom,warnings,total_hidden,reset
      if(errors)printf "%s❌ %d error signals to review; no service health assertion%s\n",red,errors,reset
    }
  '
}
