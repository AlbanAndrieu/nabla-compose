#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_API_URL="https://fastapi-sample.fastapicloud.dev"
readonly DEFAULT_DNSBL_WARN_LINES=500000
readonly DEFAULT_DNSBL_FAIL_LINES=750000
readonly DEFAULT_PY_DATA_WARN_BYTES=33554432
readonly DEFAULT_PY_DATA_FAIL_BYTES=52428800
readonly DEFAULT_UNBOUND_WARN_RSS_KB=220000
readonly DEFAULT_UNBOUND_FAIL_RSS_KB=320000
readonly DEFAULT_FREE_WARN_KB=131072
readonly DEFAULT_FREE_FAIL_KB=65536

mode=""
ssh_target="${PFSENSE_SSH_TARGET:-}"
ssh_port="${PFSENSE_SSH_PORT:-}"
api_url="${PFSENSE_FASTAPI_URL:-${DEFAULT_API_URL}}"
output_format="text"
strict=0
dnsbl_warn_lines="${PFSENSE_DNSBL_WARN_LINES:-${DEFAULT_DNSBL_WARN_LINES}}"
dnsbl_fail_lines="${PFSENSE_DNSBL_FAIL_LINES:-${DEFAULT_DNSBL_FAIL_LINES}}"
py_data_warn_bytes="${PFSENSE_PY_DATA_WARN_BYTES:-${DEFAULT_PY_DATA_WARN_BYTES}}"
py_data_fail_bytes="${PFSENSE_PY_DATA_FAIL_BYTES:-${DEFAULT_PY_DATA_FAIL_BYTES}}"
unbound_warn_rss_kb="${PFSENSE_UNBOUND_WARN_RSS_KB:-${DEFAULT_UNBOUND_WARN_RSS_KB}}"
unbound_fail_rss_kb="${PFSENSE_UNBOUND_FAIL_RSS_KB:-${DEFAULT_UNBOUND_FAIL_RSS_KB}}"
free_warn_kb="${PFSENSE_FREE_WARN_KB:-${DEFAULT_FREE_WARN_KB}}"
free_fail_kb="${PFSENSE_FREE_FAIL_KB:-${DEFAULT_FREE_FAIL_KB}}"
declare -a ssh_options=(-o BatchMode=yes -o ConnectTimeout=8)

usage() {
  cat <<'EOF'
Audit the pfSense posture established after the Netgate 1100 memory incident.

Usage:
  scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com [--json] [--strict]
  scripts/pfsense/audit-posture.sh --ssh HOST --port PORT [--json] [--strict]
  scripts/pfsense/audit-posture.sh --api [URL] [--json] [--strict]
  scripts/pfsense/audit-posture.sh --local [--json] [--strict]

Modes:
  --ssh TARGET   Full read-only audit over SSH from a workstation. SSH aliases
                 from ~/.ssh/config are supported and preferred.
  --port PORT    Override the SSH port when the target is not configured in
                 ~/.ssh/config.
  --api [URL]    Partial audit through fastapi-sample.
  --local        Pipe the same POSIX collector through local /bin/sh.

Options:
  --ssh-opt OPT  Add one ssh option. May be repeated.
  --json         Emit JSON.
  --strict       WARN also makes the command non-zero.
  -h, --help     Show this help.

Threshold overrides:
  PFSENSE_DNSBL_WARN_LINES / PFSENSE_DNSBL_FAIL_LINES
  PFSENSE_PY_DATA_WARN_BYTES / PFSENSE_PY_DATA_FAIL_BYTES
  PFSENSE_UNBOUND_WARN_RSS_KB / PFSENSE_UNBOUND_FAIL_RSS_KB
  PFSENSE_FREE_WARN_KB / PFSENSE_FREE_FAIL_KB

The defaults are capacity guardrails for the current Netgate 1100, not generic
pfSense sizing recommendations.
EOF
}

while (($# > 0)); do
  case "$1" in
    --ssh)
      [[ $# -ge 2 ]] || { echo "ERROR: --ssh requires a target" >&2; exit 64; }
      mode="ssh"
      ssh_target="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "ERROR: --port requires a port" >&2; exit 64; }
      ssh_port="$2"
      shift 2
      ;;
    --api)
      mode="api"
      if [[ $# -ge 2 && "$2" != --* ]]; then
        api_url="$2"
        shift 2
      else
        shift
      fi
      ;;
    --local)
      mode="local"
      shift
      ;;
    --ssh-opt)
      [[ $# -ge 2 ]] || { echo "ERROR: --ssh-opt requires one option" >&2; exit 64; }
      ssh_options+=("$2")
      shift 2
      ;;
    --json)
      output_format="json"
      shift
      ;;
    --strict)
      strict=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ -z "${mode}" ]]; then
  if [[ -n "${ssh_target}" ]]; then
    mode="ssh"
  else
    echo "ERROR: choose --ssh, --api, or --local" >&2
    exit 64
  fi
fi

if [[ "${mode}" == "ssh" && -z "${ssh_target}" ]]; then
  echo "ERROR: SSH mode requires a target" >&2
  exit 64
fi

if [[ -n "${ssh_port}" ]]; then
  if [[ ! "${ssh_port}" =~ ^[0-9]+$ ]] || ((ssh_port < 1 || ssh_port > 65535)); then
    echo "ERROR: --port/PFSENSE_SSH_PORT must be an integer between 1 and 65535" >&2
    exit 64
  fi
  ssh_options+=(-p "${ssh_port}")
fi

remote_collector() {
  cat <<'PFSENSE_REMOTE'
set -u

emit() {
  printf '%s	%s	%s	%s
' "$1" "$2" "$3" "$4"
}

xml_value() {
  tag="$1"
  sed -n "s:.*<${tag}>\(.*\)</${tag}>.*:\1:p" /conf/config.xml 2>/dev/null | tail -n 1
}

number_or_zero() {
  case "$1" in
    '' | *[!0-9]*) printf '0
' ;;
    *) printf '%s
' "$1" ;;
  esac
}

dnsbl_warn_lines="${PFSENSE_DNSBL_WARN_LINES:-500000}"
dnsbl_fail_lines="${PFSENSE_DNSBL_FAIL_LINES:-750000}"
py_data_warn_bytes="${PFSENSE_PY_DATA_WARN_BYTES:-33554432}"
py_data_fail_bytes="${PFSENSE_PY_DATA_FAIL_BYTES:-52428800}"
unbound_warn_rss_kb="${PFSENSE_UNBOUND_WARN_RSS_KB:-220000}"
unbound_fail_rss_kb="${PFSENSE_UNBOUND_FAIL_RSS_KB:-320000}"
free_warn_kb="${PFSENSE_FREE_WARN_KB:-131072}"
free_fail_kb="${PFSENSE_FREE_FAIL_KB:-65536}"
expected_snort_memcap=33554432

php_limit="$(php -r 'echo ini_get("memory_limit");' 2>/dev/null || true)"
if [ "$php_limit" = "128M" ]; then
  emit PASS php.memory_limit "$php_limit" "pfBlockerNG PHP budget is pinned to 128M"
else
  emit FAIL php.memory_limit "${php_limit:-missing}" "expected 128M; do not use 256M/512M as a permanent workaround"
fi

dnsbl_mode="$(xml_value dnsbl_mode)"
if [ "$dnsbl_mode" = "dnsbl_python" ]; then
  emit PASS pfblocker.dnsbl_mode "$dnsbl_mode" "DNSBL uses Unbound Python mode"
else
  emit FAIL pfblocker.dnsbl_mode "${dnsbl_mode:-missing}" "expected dnsbl_python"
fi

pfb_inc="/usr/local/pkg/pfblockerng/pfblockerng.inc"
if [ -r "$pfb_inc" ] &&
  grep -q 'pfb_unbound_py_swap_fits_ram' "$pfb_inc" &&
  grep -q 'RAM-constrained box.*using Unbound restart' "$pfb_inc"; then
  emit PASS pfblocker.dnsbl_ram_swap_gate present "package can decline a ~2x hot swap and restart Unbound on constrained RAM"
else
  emit WARN pfblocker.dnsbl_ram_swap_gate missing "verify package version before a large DNSBL rebuild; RAM-safe hot-swap fallback was not detected"
fi

pfb_tld="$(xml_value pfb_tld)"
if [ -z "$pfb_tld" ] || [ "$pfb_tld" = "off" ]; then
  emit PASS pfblocker.tld "${pfb_tld:-off}" "TLD expansion is disabled"
else
  emit WARN pfblocker.tld "$pfb_tld" "TLD processing can materially increase DNSBL memory"
fi

regdhcp="$(xml_value regdhcp)"
if [ -z "$regdhcp" ] || [ "$regdhcp" = "off" ]; then
  emit PASS unbound.dynamic_dhcp_registration "${regdhcp:-off}" "legacy dynamic DHCP registration is disabled"
else
  emit WARN unbound.dynamic_dhcp_registration "$regdhcp" "review DHCP-driven Unbound reload behavior"
fi

emit INFO unbound.static_dhcp_registration "$(xml_value regdhcpstatic)" "static DHCP mapping registration state"

module_config="$(sed -n 's/^[[:space:]]*module-config:[[:space:]]*//p' /var/unbound/unbound.conf 2>/dev/null | head -n 1)"
if printf '%s' "$module_config" | grep -q 'python validator iterator'; then
  emit PASS unbound.module_config "$module_config" "pfBlockerNG Python module ordering is correct"
else
  emit FAIL unbound.module_config "${module_config:-missing}" "expected python validator iterator"
fi

python_script="$(sed -n 's/^[[:space:]]*python-script:[[:space:]]*//p' /var/unbound/unbound.conf 2>/dev/null | head -n 1)"
if [ "$python_script" = "pfb_unbound.py" ]; then
  emit PASS unbound.python_script "$python_script" "pfBlockerNG Unbound loader is configured"
else
  emit FAIL unbound.python_script "${python_script:-missing}" "expected pfb_unbound.py"
fi

emit INFO unbound.msg_cache_size "$(sed -n 's/^[[:space:]]*msg-cache-size:[[:space:]]*//p' /var/unbound/unbound.conf 2>/dev/null | head -n 1)" "native message cache"
emit INFO unbound.rrset_cache_size "$(sed -n 's/^[[:space:]]*rrset-cache-size:[[:space:]]*//p' /var/unbound/unbound.conf 2>/dev/null | head -n 1)" "native rrset cache"

unbound_rss_kb="$(ps axo rss,command 2>/dev/null | awk '/\/usr\/local\/sbin\/unbound -c \/var\/unbound\/unbound.conf/ {print $1; exit}')"
unbound_rss_kb="$(number_or_zero "$unbound_rss_kb")"
if [ "$unbound_rss_kb" -ge "$unbound_fail_rss_kb" ]; then
  emit FAIL unbound.rss_kb "$unbound_rss_kb" "Unbound RSS exceeds the fail guardrail"
elif [ "$unbound_rss_kb" -ge "$unbound_warn_rss_kb" ]; then
  emit WARN unbound.rss_kb "$unbound_rss_kb" "Unbound RSS leaves limited reload/Snort headroom"
elif [ "$unbound_rss_kb" -gt 0 ]; then
  emit PASS unbound.rss_kb "$unbound_rss_kb" "Unbound RSS is below the warning guardrail"
else
  emit FAIL unbound.rss_kb "0" "Unbound process was not found"
fi

native_cache_bytes="$(unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | awk -F= '/^mem\./ {sum += $2} END {printf "%.0f", sum + 0}')"
native_cache_bytes="$(number_or_zero "$native_cache_bytes")"
emit INFO unbound.native_cache_bytes "$native_cache_bytes" "sum of native mem.* counters; Python DNSBL allocations are separate"

page_count="$(number_or_zero "$(sysctl -n vm.stats.vm.v_free_count 2>/dev/null || printf '0')")"
page_size="$(number_or_zero "$(sysctl -n hw.pagesize 2>/dev/null || printf '4096')")"
free_kb=$((page_count * page_size / 1024))
if [ "$free_kb" -le "$free_fail_kb" ]; then
  emit FAIL memory.free_kb "$free_kb" "free memory is inside the critical OOM guardrail"
elif [ "$free_kb" -le "$free_warn_kb" ]; then
  emit WARN memory.free_kb "$free_kb" "free memory is below preferred steady-state headroom"
else
  emit PASS memory.free_kb "$free_kb" "free memory is above the warning guardrail"
fi

swap_used_kb="$(swapinfo -k 2>/dev/null | awk 'NR > 1 {sum += $3} END {print sum + 0}')"
emit INFO memory.swap_used_kb "$(number_or_zero "$swap_used_kb")" "swap is not used as the memory-safety mechanism"

oom_count="$(dmesg 2>/dev/null | egrep -ic 'killed|failed to reclaim|waited too long|out of swap' || true)"
oom_count="$(number_or_zero "$oom_count")"
if [ "$oom_count" -gt 0 ]; then
  emit WARN kernel.oom_evidence "$oom_count" "current boot log contains OOM/reclaim evidence"
else
  emit PASS kernel.oom_evidence "0" "no OOM/reclaim signature found in current dmesg"
fi

dnsbl_lines=0
for file in /var/db/pfblockerng/dnsbl/*.txt; do
  [ -f "$file" ] || continue
  lines="$(number_or_zero "$(wc -l <"$file" 2>/dev/null || printf '0')")"
  dnsbl_lines=$((dnsbl_lines + lines))
done

loaded_entries=0
if [ -r /var/unbound/pfb_py_count ]; then
  loaded_entries="$(number_or_zero "$(tr -dc '0-9' </var/unbound/pfb_py_count 2>/dev/null)")"
fi

if [ "$loaded_entries" -ge "$dnsbl_fail_lines" ]; then
  emit FAIL pfblocker.dnsbl_loaded_entries "$loaded_entries" "active Python DNSBL snapshot exceeds the fail guardrail"
elif [ "$loaded_entries" -ge "$dnsbl_warn_lines" ]; then
  emit WARN pfblocker.dnsbl_loaded_entries "$loaded_entries" "active Python DNSBL snapshot remains large for 1 GiB RAM"
elif [ "$loaded_entries" -gt 0 ]; then
  emit PASS pfblocker.dnsbl_loaded_entries "$loaded_entries" "active Python DNSBL snapshot is below the warning guardrail"
else
  emit WARN pfblocker.dnsbl_loaded_entries 0 "pfb_py_count is absent or empty; use the latest DNSBL PASSED marker as fallback evidence"
fi

if [ "$dnsbl_lines" -eq 0 ] && [ "$loaded_entries" -gt 0 ]; then
  emit INFO pfblocker.dnsbl_staged_lines 0 "no staged *.txt lines are present, but the previous Python snapshot is still active"
elif [ "$dnsbl_lines" -ge "$dnsbl_fail_lines" ]; then
  emit FAIL pfblocker.dnsbl_staged_lines "$dnsbl_lines" "staged DNSBL feed lines exceed the fail guardrail"
elif [ "$dnsbl_lines" -ge "$dnsbl_warn_lines" ]; then
  emit WARN pfblocker.dnsbl_staged_lines "$dnsbl_lines" "staged DNSBL feed lines remain large for 1 GiB RAM"
else
  emit PASS pfblocker.dnsbl_staged_lines "$dnsbl_lines" "staged DNSBL feed lines are below the warning guardrail"
fi

ut1_selected="$(sed -n '/<pfblockerngblacklist>/,/<\/pfblockerngblacklist>/p' /conf/config.xml 2>/dev/null | sed -n 's:.*<selected>\(.*\)</selected>.*:\1:p' | head -n 1)"
for category in adult malware gambling games dating; do
  if printf ',%s,' "$ut1_selected" | grep -q ",${category},"; then
    emit FAIL "pfblocker.ut1_category.${category}" enabled "UT1 category is expected disabled for the Netgate 1100 memory policy"
  else
    emit PASS "pfblocker.ut1_category.${category}" disabled "UT1 category is not selected"
  fi
done

py_data="/var/unbound/pfb_py_data.txt"
if [ -f "$py_data" ]; then
  py_data_bytes="$(number_or_zero "$(stat -f %z "$py_data" 2>/dev/null || printf '0')")"
  if [ "$py_data_bytes" -ge "$py_data_fail_bytes" ]; then
    emit FAIL pfblocker.python_loader_bytes "$py_data_bytes" "pfb_py_data.txt exceeds the fail guardrail"
  elif [ "$py_data_bytes" -ge "$py_data_warn_bytes" ]; then
    emit WARN pfblocker.python_loader_bytes "$py_data_bytes" "loader file is large; Python structures can be much larger"
  else
    emit PASS pfblocker.python_loader_bytes "$py_data_bytes" "loader file is below the warning guardrail"
  fi
else
  emit FAIL pfblocker.python_loader_bytes "missing" "pfb_py_data.txt was not found"
fi

for feed in Gambling EasyList_Norwegian_Danish_Icelandic; do
  path="/var/db/pfblockerng/dnsbl/${feed}.txt"
  if [ -f "$path" ]; then
    lines="$(number_or_zero "$(wc -l <"$path" 2>/dev/null || printf '0')")"
  else
    lines=0
  fi
  if [ "$lines" -gt 0 ]; then
    emit WARN "pfblocker.feed_artifact.${feed}" "$lines" "staged artifact still contributes entries; verify group/source state after reload"
  else
    emit PASS "pfblocker.feed_artifact.${feed}" 0 "feed artifact contributes no staged entries"
  fi
done

last_dnsbl_pass="$(grep -E 'DNSBL update.*PASSED' /var/log/pfblockerng/pfblockerng.log 2>/dev/null | tail -n 1 | tr '\t\r\n' '   ')"
if [ -n "$last_dnsbl_pass" ]; then
  emit INFO pfblocker.last_dnsbl_pass present "$last_dnsbl_pass"
else
  emit WARN pfblocker.last_dnsbl_pass missing "no DNSBL PASSED marker found"
fi

update_start="$(number_or_zero "$(grep -n 'UPDATE PROCESS START' /var/log/pfblockerng/pfblockerng.log 2>/dev/null | tail -n 1 | cut -d: -f1)")"
update_end="$(number_or_zero "$(grep -n 'UPDATE PROCESS ENDED' /var/log/pfblockerng/pfblockerng.log 2>/dev/null | tail -n 1 | cut -d: -f1)")"
if [ "$update_start" -eq 0 ]; then
  emit INFO pfblocker.last_update_completion unknown "no UPDATE PROCESS START marker found"
elif [ "$update_end" -ge "$update_start" ]; then
  emit PASS pfblocker.last_update_completion complete "latest update has an END marker"
else
  emit WARN pfblocker.last_update_completion incomplete "latest START has no later END marker"
fi

snort_conf="$(find /usr/local/etc/snort -type f -path '*mvneta0.4090/snort.conf' 2>/dev/null | head -n 1)"
if [ -n "$snort_conf" ]; then
  snort_memcap="$(grep -A12 'preprocessor http_inspect: global' "$snort_conf" 2>/dev/null | sed -n 's/.*memcap[[:space:]]\([0-9][0-9]*\).*/\1/p' | head -n 1)"
  snort_memcap="$(number_or_zero "$snort_memcap")"
  if [ "$snort_memcap" -eq "$expected_snort_memcap" ]; then
    emit PASS snort.http_inspect_memcap "$snort_memcap" "WAN HTTP Inspect memcap remains 32 MiB"
  else
    emit FAIL snort.http_inspect_memcap "$snort_memcap" "expected 33554432 bytes"
  fi
else
  emit WARN snort.http_inspect_memcap missing "WAN generated snort.conf was not found"
fi

if pgrep -x snort >/dev/null 2>&1; then
  emit INFO service.snort running "keep WAN-only and verify memory headroom"
else
  emit INFO service.snort stopped "acceptable during memory remediation"
fi

if pgrep -x ntopng >/dev/null 2>&1; then
  emit FAIL service.ntopng running "ntopng must remain offloaded from the Netgate 1100"
else
  emit PASS service.ntopng stopped "ntopng is not consuming pfSense memory"
fi

softflowd_enable="$(sed -n '/<softflowd>/,/<\/softflowd>/p' /conf/config.xml 2>/dev/null | sed -n 's:.*<enable>\(.*\)</enable>.*:\1:p' | tail -n 1)"
if pgrep -x softflowd >/dev/null 2>&1; then
  emit FAIL service.softflowd running "native pflow replaces softflowd"
elif [ -z "$softflowd_enable" ] || [ "$softflowd_enable" = "off" ]; then
  emit PASS service.softflowd "${softflowd_enable:-off}" "legacy softflowd is disabled"
else
  emit WARN service.softflowd "$softflowd_enable" "config enables softflowd although no process runs"
fi

pflow_output="$(pflowctl -v -l 2>/dev/null || true)"
if printf '%s\n' "$pflow_output" | grep -q 'version 10 domain 1 src 172\.17\.0\.1 dst 172\.17\.0\.24:2055'; then
  emit PASS pflow.truenas configured "IPFIX domain 1 exports to TrueNAS/Akvorado"
else
  emit FAIL pflow.truenas missing "expected domain 1 to 172.17.0.24:2055"
fi
if printf '%s\n' "$pflow_output" | grep -q 'version 10 domain 2 .*dst 162\.159\.65\.1:2055'; then
  emit PASS pflow.cloudflare configured "IPFIX domain 2 exports to Cloudflare Network Flow"
else
  emit FAIL pflow.cloudflare missing "expected domain 2 to 162.159.65.1:2055"
fi
connected_count="$(number_or_zero "$(printf '%s\n' "$pflow_output" | grep -c 'socket: connected' || true)")"
if [ "$connected_count" -ge 2 ]; then
  emit PASS pflow.connected_exporters "$connected_count" "both expected exporters report connected sockets"
else
  emit WARN pflow.connected_exporters "$connected_count" "fewer than two exporters report connected"
fi

if pgrep -x kea-dhcp4 >/dev/null 2>&1; then
  emit PASS service.kea_dhcp4 running "Kea DHCPv4 is running"
else
  emit FAIL service.kea_dhcp4 stopped "investigate core DHCP before optional analytics"
fi

if pgrep -x zabbix_agentd >/dev/null 2>&1; then
  emit PASS service.zabbix_agentd running "Zabbix agent is running"
else
  emit WARN service.zabbix_agentd stopped "restore monitoring only after core memory headroom is stable"
fi

pfb_filter_count="$(number_or_zero "$(pgrep -f 'php_pfb.*filterlog' 2>/dev/null | wc -l | tr -d ' ')")"
if [ "$pfb_filter_count" -eq 1 ]; then
  emit PASS service.pfb_filter "$pfb_filter_count" "exactly one pfBlockerNG filterlog helper runs"
elif [ "$pfb_filter_count" -gt 1 ]; then
  emit FAIL service.pfb_filter "$pfb_filter_count" "duplicate filterlog helpers waste memory"
else
  emit WARN service.pfb_filter 0 "pfBlockerNG filterlog helper is not running"
fi
PFSENSE_REMOTE
}

api_collector() {
  local base="${api_url%/}"
  local payload healthz configured reachable

  command -v curl >/dev/null 2>&1 || {
    printf 'FAIL\tapi.curl\tmissing\tcurl is required for API mode\n'
    return
  }
  command -v jq >/dev/null 2>&1 || {
    printf 'FAIL\tapi.jq\tmissing\tjq is required for API mode\n'
    return
  }

  if ! payload="$(curl -fsS --max-time 12 "${base}/api/homelab/health")"; then
    printf 'FAIL\tapi.homelab_health\tunreachable\tfastapi-sample /api/homelab/health request failed\n'
    return
  fi

  if jq -e '.pfsense != null' >/dev/null 2>&1 <<<"${payload}"; then
    printf 'PASS\tapi.pfsense_snapshot\tpresent\tfastapi-sample returned a pfSense homelab snapshot\n'
  else
    printf 'FAIL\tapi.pfsense_snapshot\tmissing\t/api/homelab/health did not contain .pfsense\n'
  fi

  configured="$(jq -r '.pfsense.dns.configured // .pfsense.configured // "unknown"' <<<"${payload}")"
  reachable="$(jq -r '.pfsense.dns.reachable // .pfsense.reachable // "unknown"' <<<"${payload}")"
  printf 'INFO\tapi.pfsense_configured\t%s\tposture reported by fastapi-sample\n' "${configured}"
  printf 'INFO\tapi.pfsense_reachable\t%s\tposture reported by fastapi-sample\n' "${reachable}"

  if healthz="$(curl -fsS --max-time 12 "${base}/healthz" 2>/dev/null)"; then
    if jq -e '.checks.pfsense != null' >/dev/null 2>&1 <<<"${healthz}"; then
      printf 'PASS\tapi.healthz_pfsense\tpresent\t/healthz contains the bounded pfSense check\n'
    else
      printf 'WARN\tapi.healthz_pfsense\tmissing\t/healthz did not expose checks.pfsense\n'
    fi
  else
    printf 'WARN\tapi.healthz_pfsense\tunreachable\t/healthz request failed\n'
  fi

  printf 'SKIP\tappliance.full_posture\tnot_exposed\tconfig.xml, RSS, DNSBL files, Snort memcap and pflowctl require SSH/local evidence today\n'
}

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

case "${mode}" in
  ssh)
    remote_collector |
      ssh "${ssh_options[@]}" "${ssh_target}" env \
        "PFSENSE_DNSBL_WARN_LINES=${dnsbl_warn_lines}" \
        "PFSENSE_DNSBL_FAIL_LINES=${dnsbl_fail_lines}" \
        "PFSENSE_PY_DATA_WARN_BYTES=${py_data_warn_bytes}" \
        "PFSENSE_PY_DATA_FAIL_BYTES=${py_data_fail_bytes}" \
        "PFSENSE_UNBOUND_WARN_RSS_KB=${unbound_warn_rss_kb}" \
        "PFSENSE_UNBOUND_FAIL_RSS_KB=${unbound_fail_rss_kb}" \
        "PFSENSE_FREE_WARN_KB=${free_warn_kb}" \
        "PFSENSE_FREE_FAIL_KB=${free_fail_kb}" \
        /bin/sh >"${tmp}"
    ;;
  local)
    remote_collector |
      env \
        "PFSENSE_DNSBL_WARN_LINES=${dnsbl_warn_lines}" \
        "PFSENSE_DNSBL_FAIL_LINES=${dnsbl_fail_lines}" \
        "PFSENSE_PY_DATA_WARN_BYTES=${py_data_warn_bytes}" \
        "PFSENSE_PY_DATA_FAIL_BYTES=${py_data_fail_bytes}" \
        "PFSENSE_UNBOUND_WARN_RSS_KB=${unbound_warn_rss_kb}" \
        "PFSENSE_UNBOUND_FAIL_RSS_KB=${unbound_fail_rss_kb}" \
        "PFSENSE_FREE_WARN_KB=${free_warn_kb}" \
        "PFSENSE_FREE_FAIL_KB=${free_fail_kb}" \
        /bin/sh >"${tmp}"
    ;;
  api)
    api_collector >"${tmp}"
    ;;
esac

if [[ "${output_format}" == "json" ]]; then
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required for --json" >&2; exit 69; }
  python3 - "${tmp}" <<'PY'
import json
import sys

rows = []
with open(sys.argv[1], encoding="utf-8") as handle:
    for raw in handle:
        parts = raw.rstrip("\n").split("\t", 3)
        if len(parts) != 4:
            continue
        level, key, value, message = parts
        rows.append({"level": level, "key": key, "value": value, "message": message})

counts = {}
for row in rows:
    counts[row["level"]] = counts.get(row["level"], 0) + 1

print(json.dumps({"schema": "nabla.pfsense.posture.v1", "counts": counts, "checks": rows}, indent=2, sort_keys=True))
PY
else
  printf '%-5s %-38s %-18s %s\n' "LEVEL" "CHECK" "VALUE" "MESSAGE"
  printf '%-5s %-38s %-18s %s\n' "-----" "--------------------------------------" "------------------" "-------"
  while IFS=$'\t' read -r level key value message; do
    [[ -n "${level}" ]] || continue
    printf '%-5s %-38s %-18s %s\n' "${level}" "${key}" "${value}" "${message}"
  done <"${tmp}"
fi

failures="$(awk -F '\t' '$1 == "FAIL" {count++} END {print count + 0}' "${tmp}")"
warnings="$(awk -F '\t' '$1 == "WARN" {count++} END {print count + 0}' "${tmp}")"

if ((failures > 0)); then
  exit 1
fi
if ((strict == 1 && warnings > 0)); then
  exit 2
fi
