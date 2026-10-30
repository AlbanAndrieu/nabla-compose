#!/usr/bin/env bash
# Netgate 1100 memory-pressure sampler. Runs from the operator workstation.
# Read-only single SSH session, bounded samples; no logs or process args copied.
set -euo pipefail
# shellcheck source=scripts/pfsense/console.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/console.sh"
usage() { printf 'Usage: %s --check [--samples 1..16] [--interval-seconds 5..30] [--target SSH_ALIAS] [--port PORT]\n' "$0"; }
case "${1:-}" in
  --check) shift ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
samples=1
interval=15
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
while (($#)); do
  case "$1" in
    --samples) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; samples="$2"; shift 2 ;;
    --interval-seconds) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; interval="$2"; shift 2 ;;
    --target) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "${samples}" =~ ^[0-9]{1,2}$ && "${interval}" =~ ^[0-9]{1,2}$ ]] || { echo 'Invalid sampling budget' >&2; exit 2; }
samples=$((10#${samples}))
interval=$((10#${interval}))
((samples>=1 && samples<=16 && interval>=5 && interval<=30 && (samples-1)*interval<=240)) || { echo 'Sampling exceeds safe limit' >&2; exit 2; }
[[ "${target}" =~ ^[A-Za-z0-9._@-]+$ ]] || { echo 'Invalid SSH target' >&2; exit 2; }
if [[ -n "${port}" ]]; then
  [[ "${port}" =~ ^[0-9]{1,5}$ ]] || { echo 'Invalid SSH port' >&2; exit 2; }
  port=$((10#${port}))
  ((port>=1 && port<=65535)) || { echo 'Invalid SSH port' >&2; exit 2; }
fi
args=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)
[[ -z "${port}" ]] || args+=(-p "${port}")
pfsense_ui_banner "OOM process attribution · read-only · bounded"
# Validated numeric bounds become remote sampler argv.
# shellcheck disable=SC2029
ssh "${args[@]}" "${target}" "/bin/sh -s -- ${samples} ${interval}" <<'REMOTE' | pfsense_ui_render
set -eu
samples=$1
interval=$2
echo '=== Memory-pressure time-series (instantaneous; not PID kill provenance) ==='
echo "sampler_budget=samples=$samples interval_seconds=$interval"
i=1
while [ "$i" -le "$samples" ]; do
  stamp=$(date '+%Y-%m-%dT%H:%M:%S%z')
  free=$(sysctl -n vm.stats.vm.v_free_count 2>/dev/null) || { echo 'ERROR: sampler_sysctl_failed'; exit 71; }
  inactive=$(sysctl -n vm.stats.vm.v_inactive_count 2>/dev/null) || { echo 'ERROR: sampler_sysctl_failed'; exit 71; }
  page_size=$(sysctl -n vm.stats.vm.v_page_size 2>/dev/null) || { echo 'ERROR: sampler_sysctl_failed'; exit 71; }
  case "$free:$inactive:$page_size" in *[!0-9:]*|:*|*::*|*:) echo 'ERROR: sampler_sysctl_invalid'; exit 71 ;; esac
  [ "$page_size" -gt 0 ] || { echo 'ERROR: sampler_sysctl_invalid'; exit 71; }
  available_kib=$(((free+inactive)*page_size/1024))
  printf 'sample_seq=%d timestamp=%s available_kib=%d free_kib=%d inactive_kib=%d\n' \
    "$i" "$stamp" "$available_kib" "$((free*page_size/1024))" "$((inactive*page_size/1024))"
  if [ "$available_kib" -lt 65536 ]; then
    echo 'WARN: sampled_memory_headroom=CRITICAL_BELOW_64_MIB'
  elif [ "$available_kib" -lt 131072 ]; then
    echo 'WARN: sampled_memory_headroom=LOW_BELOW_128_MIB'
  else
    echo 'sampled_memory_headroom=ABOVE_128_MIB'
  fi
  processes=$(ps axo rss,pcpu,comm 2>/dev/null) || { echo 'ERROR: sampler_ps_failed'; exit 71; }
  printf '%s\n' "$processes" | LC_ALL=C awk '
    NR==1 {next}
    $1 !~ /^[0-9]+$/ {next}
    {
      name=$3
      sub(/^.*\//, "", name)
      category=""
      if(name=="unbound") category="unbound"
      else if(name=="snort") category="snort"
      else if(name=="php" || name=="php-cgi") category="php_cli"
      else if(name ~ /^php-fpm/) category="php_fpm"
      else if(name ~ /^php_pfb/) category="php_pfb"
      else if(name ~ /^crowdsec/) category="crowdsec"
      else if(name=="haproxy") category="haproxy"
      else if(name=="lighttpd_pfb") category="lighttpd_pfb"
      if(category!="") { rss[category]+=$1; count[category]++; cpu[category]+=$2 }
    }
    END {
      split("unbound snort php_cli php_fpm php_pfb crowdsec haproxy lighttpd_pfb", categories, " ")
      for(i=1;i<=8;i++) {
        cat=categories[i]
        printf "process_group=%s rss_sum_kib=%d processes=%d cpu_pct_sum=%.1f\n",cat,rss[cat]+0,count[cat]+0,cpu[cat]+0
      }
    }
  '
  i=$((i+1))
  if [ "$i" -le "$samples" ]; then sleep "$interval"; fi
done
echo 'rss_sum_is_not_unique_physical_ram=yes'
echo 'sample_scope=INSTANT_ONLY_PROCESS_NAMES_NO_ARGS'
echo 'attribution=NOT_PROVEN_WITHOUT_MATCHED_OOM_KERNEL_LOG'
echo '=== End of bounded memory-pressure sampling ==='
REMOTE
