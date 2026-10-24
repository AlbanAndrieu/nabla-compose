#!/usr/bin/env bash
# Netgate 1100: bounded, read-only Unbound / pfBlockerNG / WhatsApp triage.
# Run on operator workstation. Does not reload DNSBL or change the firewall.
set -euo pipefail
# Workstation-only console; the pfSense /bin/sh collector stays plain.
# shellcheck source=scripts/pfsense/console.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/console.sh"

target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
usage() {
  printf 'Usage: %s --check [--target SSH_ALIAS] [--port SSH_PORT]\n' "$0"
}
case "${1:-}" in
  --check) shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
while (($#)); do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 && "$2" =~ ^[0-9]{1,5}$ ]] || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "${target}" =~ ^[a-zA-Z0-9._@-]+$ ]] || { echo 'Invalid SSH target' >&2; exit 2; }
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)
[[ -z "${port}" ]] || ssh_opts+=(-p "${port}")
pfsense_ui_banner "Unbound, Snort and CrowdSec · read-only"
ssh "${ssh_opts[@]}" "${target}" '/bin/sh -s' <<'REMOTE' | pfsense_ui_render
set -u
# Never dump config.xml, full resolver configuration, pfBlockerNG lists or user queries.
echo '=== pfSense UTC/local time and uptime ==='
date; uptime
echo '=== Jobs scheduled near repeated 02:10 OOM (schedule + type only) ==='
# Restrict output to hour/minute/type; do not print raw crontab arguments.
if [ -r /etc/crontab ]; then
  awk '
    /^[[:space:]]*#/ || NF < 7 { next }
    {
      task = ""
      for (i=7; i<=NF; i++) {
        if ($i ~ /snort_check_for_rule_updates/) task="snort_rules_update"
        else if ($i ~ /snort_check_cron_misc/) task="snort_housekeeping"
        if ($i ~ /pfblockerng.php/) task="pfblockerng"
        if ($i ~ /servicewatchdog_cron/) task="servicewatchdog"
        if ($i ~ /crowdsec/) task="crowdsec"
      }
      if (task != "") printf "cron_minute=%s cron_hour=%s cron_day=%s task=%s\n", $1, $2, $3, task
    }
  ' /etc/crontab | head -20
fi
echo '=== Snort updater evidence: log file timestamps only, no rule contents ==='
# Snort rules updates may cause a resource-intensive rebuild. File timestamps
# indicate possible activity but are NOT proof of Snort causing an OOM.
for f in /var/log/snort/snort_updates.log /var/log/snort/snort_updates.log.0 \
         /var/log/snort/snort_rules_update.log; do
  [ -f "$f" ] || continue
  stat -f 'snort_log_file=%N modified=%Sm size_bytes=%z' \
    -t '%Y-%m-%dT%H:%M:%S%z' "$f" 2>/dev/null || true
done

echo '=== Snort/pfBlockerNG/kernel OOM chronology (redacted, bounded) ==='
# Log entries show temporal proximity, not proof of process RSS or causation.
for file in /var/log/cron.log /var/log/cron.log.0 /var/log/system.log /var/log/system.log.0 /var/log/snort/snort_rules_update.log; do
  [ -r "$file" ] || continue
  case "$file" in *cron*) source=cron ;; *snort*) source=snort ;; *) source=system ;; esac
  printf 'log_source=%s readable=yes\n' "$source"
  tail -n 5000 "$file" | awk -v source="$source" '
    function stamp(line, s) {
      s=line
      # pfSense/FreeBSD syslog RFC5424: <PRI>VERSION ISO8601 HOST ...
      # Do not log arbitrary messages or extract timestamps from arguments.
      sub(/^<[0-9]+>[0-9]+[[:space:]]+/, "", s)
      if (match(s, /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9](\.[0-9]+)?([+-][0-9][0-9]:[0-9][0-9]|Z)?/)) return substr(s,RSTART,RLENGTH)
      if (match(s, /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/)) return substr(s,RSTART,RLENGTH)
      if (match(s, /^[A-Z][a-z][a-z] [ 0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/)) return substr(s,RSTART,RLENGTH)
      if (match(s, /^[0-9][0-9]\/[0-9][0-9]\/[0-9][0-9][0-9][0-9][[:space:]]+[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/)) return substr(s,RSTART,RLENGTH)
      return "unknown"
    }
    {
      kind=""
      if (source=="cron") {
        if ($0 ~ /snort_check_for_rule_updates/) kind="snort_cron"
        else if ($0 ~ /pfblockerng[.]php/) kind="pfblocker_cron"
      } else if (source=="system") {
        if ($0 ~ /failed to reclaim memory|out of swap|waited too long to allocate a page/) kind="kernel_oom"
        else if ($0 ~ /[Cc]rowd[Ss]ec/ && $0 ~ /[Ss]tart|[Rr]estart|[Ss]top/) kind="crowdsec_lifecycle_log"
      } else if (source=="snort") {
        if ($0 ~ /[Ss]tart|[Bb]egin|[Cc]hecking/) kind="snort_update_start"
        else if ($0 ~ /[Cc]omplet|[Ff]inish|[Ff]ail|[Ee]rror/) kind="snort_update_end_or_error"
      }
      if (kind!="") printf "source=%s event=%s timestamp=%s\n", source, kind, stamp($0)
    }
  ' | tail -24 || true
done
echo '=== CrowdSec engine vs firewall bouncer (separate processes) ==='
ps axo pid,rss,pcpu,command |
  awk '
    /crowdsec -c / {print "crowdsec_engine_pid="$1, "rss_kb="$2, "cpu_pct="$3; found=1}
    /crowdsec-firewall-bouncer -c / {print "crowdsec_bouncer_pid="$1, "rss_kb="$2, "cpu_pct="$3}
    END {if (!found) print "crowdsec_engine=not_observed"}
  ' | head -5
echo '=== CrowdSec rc startup flags (policy hint, not proven start cause) ==='
if command -v sysrc >/dev/null 2>&1; then
  for key in crowdsec_enable crowdsec_firewall_bouncer_enable; do
    # Read-only getter. Never print the raw rc configuration.
    value=$(sysrc -n "$key" 2>/dev/null || true)
    case "$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')" in
      yes|true|on|1) state=enabled ;;
      no|false|off|0) state=disabled ;;
      *) state=unknown ;;
    esac
    printf 'rc_setting=%s status=%s\n' "$key" "$state"
  done
fi
echo '=== Recent CrowdSec pressure signatures (counts only) ==='
for file in /var/log/crowdsec/crowdsec.log /var/log/crowdsec.log; do
  [ -r "$file" ] || continue
  grep -Ec 'pf-scan-multi_ports.*(stuck|failed_sent|attempts)' "$file" 2>/dev/null |
    awk '{print "crowdsec_stuck_lines="$1}'
done
echo '=== Unbound daemon and readiness ==='
ps axo pid,lstart,rss,pcpu,command | grep '[u]nbound -c /var/unbound/unbound.conf' | head -3 || true
unbound-control -c /var/unbound/unbound.conf status 2>/dev/null | head -8 || true
sockstat -4 -l 2>/dev/null | grep -E '([.:]53[[:space:]]|[.]53[[:space:]])' | head -8 || true
echo '=== Memory budget and OOM evidence (check timestamps) ==='
sysctl vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null || true
swapinfo -h 2>/dev/null || true
# FreeBSD ps does not support GNU multi-column header suppression (pid=,rss=,...).
# Use its native column headers; filter numeric PID/RSS, omit all arguments.
printf 'pid rss_kb cpu_pct executable\n'
ps axo pid,rss,pcpu,comm 2>/dev/null |
  awk 'NR > 1 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ {
    printf "%s %s %s %s\n", $1, $2, $3, $4
  }' | sort -nr -k2 | head -15 || true
dmesg -a 2>/dev/null | grep -Ei 'failed to reclaim|out of swap|killed.*(unbound|php|netstat)|memory allocation failure' | tail -22 || true
echo '=== PHP-FPM worker footprint (RSS KiB, not additive physical RAM) ==='
# Names and counts only: do not publish worker command-line parameters or
# full per-user process details. RSS can double-count shared library pages.
ps axo rss,command 2>/dev/null | awk '
  /php-fpm: pool nginx/ {
    workers++
    rss_sum += $1
    if ($1 > max_rss) max_rss = $1
  }
  END {
    printf "php_fpm_workers=%d php_fpm_rss_sum_kb=%.0f php_fpm_max_worker_rss_kb=%.0f\n", workers + 0, rss_sum + 0, max_rss + 0
  }
'
echo '=== RAM-backed /tmp and /var capacity (filesystem metadata only) ==='
df -k /tmp /var 2>/dev/null | head -4 || true
echo '=== pfBlockerNG process overlap and historical DNSBL update markers ==='
# Classify helpers without exposing process arguments.
ps axo pid,rss,pcpu,command | awk '
  /pfblockerng[.]php/ && !/awk/ {kind="pfblockerng"}
  /php_pfb/ && !/awk/ {kind="php_pfb"}
  /pfb_unbound/ && !/awk/ {kind="pfb_unbound"}
  kind != "" {
    printf "process_class=%s pid=%s rss_kb=%s cpu_pct=%s\n",
      kind, $1, $2, $3
  }
  {kind=""}
' | head -10 || true
for file in /var/log/pfblockerng/pfblockerng.log /var/log/pfblockerng/pfblockerng.log.0; do
  if [ -r "$file" ]; then
    echo 'pfblockerng_log_present=yes'
    # Deliberately omit arbitrary domain lists, URLs, block reports and secrets.
    # Log lines can contain feed URLs, private domains or credentials.
    awk '
      /UPDATE PROCESS ENDED/ {kind="update_ended"}
      /DNSBL.*PASSED/ {kind="dnsbl_passed"}
      /DNSBL.*FAILED/ {kind="dnsbl_failed"}
      /Restarting DNSBL Service/ {kind="dnsbl_restart"}
      /Downloading.*IPinfo/ {kind="ipinfo_attempt"}
      /pfb.*out of memory/ {kind="oom_reported"}
      kind != "" {printf "pfblocker_event=%s line=%d\n", kind, NR}
      {kind=""}
    ' "$file" | tail -18 || true
  fi
done
echo '=== Resolver failures, including archived logs (limited messages) ==='
for file in /var/log/system.log /var/log/system.log.0 /var/log/resolver.log /var/log/resolver.log.0; do
  [ -r "$file" ] || continue
  grep -Ei 'unbound.*(killed|fatal|restart|exit|signal|failed|error)|failed to reclaim|out of swap|address already in use' "$file" 2>/dev/null | tail -10 || true
done
echo '=== pfBlockerNG persisted settings: flags only, never tokens/feeds ==='
if command -v php >/dev/null 2>&1; then
  php -r '
    $xml = @simplexml_load_file("/conf/config.xml");
    if ($xml === false) { echo "config=unavailable\n"; exit; }
    $p = $xml->installedpackages;
    $configs = array(
      "pfblockerng" => $p->pfblockerng->config[0] ?? null,
      "dnsbl" => $p->pfblockerngdnsblsettings->config[0] ?? null,
    );
    foreach ($configs as $label => $cfg) {
      if ($cfg === null) { echo $label, "=missing\n"; continue; }
      foreach (array("enable_cb", "pfb_dnsbl", "pfb_tld",
        "asn_reporting", "pfb_interval", "pfb_dailystart") as $key) {
        if (isset($cfg->$key)) {
          $value = strtolower(trim((string)$cfg->$key));
          if ($key === "asn_reporting") {
            $value = $value === "disabled" ? "disabled" : "enabled_or_unknown";
          } elseif ($key === "pfb_interval" || $key === "pfb_dailystart") {
            $value = $value !== "" ? "configured" : "empty";
          } else {
            $value = in_array($value, array("on", "enabled", "true", "1"),
              true) ? "enabled" : "disabled_or_unknown";
          }
          echo $label, ".", $key, "=", $value, "\n";
        }
      }
    }
  ' 2>/dev/null || true
fi
echo '=== Resolver mode (generated config markers only) ==='
if [ -r /var/unbound/unbound.conf ]; then
  grep -E 'module-config:|python-script:|msg-cache-size:|rrset-cache-size:' /var/unbound/unbound.conf |
    sed -E 's#(python-script:).*#\1 [configured]#' | head -12 || true
fi
echo '=== pfBlockerNG DNSBL largest inputs (file metadata only) ==='
if [ -d /var/db/pfblockerng/dnsblorig ]; then
  # Avoid a pipeline in a shell loop that prints all feeds when newline
  # escapes are wrong. Keep bounded output without exposing feed contents.
  for f in /var/db/pfblockerng/dnsblorig/*; do
    [ -f "$f" ] || continue
    case "$f" in *.md5|*.raw|*.sha*) continue ;; esac
    size=$(stat -f %z "$f" 2>/dev/null || echo 0)
    printf '%s %s\n' "$size" "$(basename "$f")"
  done | sort -nr | head -10 || true
fi
echo '=== Unbound metrics (no counter reset) ==='
unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null |
  grep -E '^(total.num.queries=|total.num.queries_timed_out=|total.num.queries_discard_timeout=|total.num.cachehits=|total.num.cachemiss=|mem[.])' | head -30 || true
echo '=== DNS response comparison: WhatsApp public domains (no customer data) ==='
for host in whatsapp.com web.whatsapp.com static.whatsapp.net mmg.whatsapp.net; do
  echo "dns_name=$host"
  # Extract status and returned address only for known static hostnames.
  for server in 127.0.0.1 1.1.1.1; do
    answer=$(drill -t A "$host" @"$server" 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -5)
    case "$server" in
      127.0.0.1) label=unbound ;;
      *) label=control ;;
    esac
    printf '  resolver=%s %s\n' "$label" "${answer:-no_response}"
  done
done
echo '=== End of read-only triage ==='
REMOTE
