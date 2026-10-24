#!/usr/bin/env bash
# Netgate 1100: bounded, read-only Unbound / pfBlockerNG / WhatsApp triage.
# Run on operator workstation. Does not reload DNSBL or change the firewall.
set -euo pipefail

target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
usage() {
  printf 'Usage: %s --check [--target SSH_ALIAS] [--port SSH_PORT]\n' "$0" >&2
}
case "${1:-}" in
  --check) shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac
while (($#)); do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 && "$2" =~ ^[0-9]{1,5}$ ]] || { usage; exit 2; }; port="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$target" =~ ^[a-zA-Z0-9._@-]+$ ]] || { echo 'Invalid SSH target' >&2; exit 2; }
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)
[[ -z "$port" ]] || ssh_opts+=(-p "$port")
ssh "${ssh_opts[@]}" "$target" '/bin/sh -s' <<'REMOTE'
set -u
# Never dump config.xml, full resolver configuration, pfBlockerNG lists or user queries.
echo '=== pfSense UTC/local time and uptime ==='
date; uptime
echo '=== Unbound daemon and readiness ==='
ps axo pid,lstart,rss,pcpu,command | grep '[u]nbound -c /var/unbound/unbound.conf' | head -3 || true
unbound-control -c /var/unbound/unbound.conf status 2>/dev/null | head -8 || true
sockstat -4 -l 2>/dev/null | grep -E '([.:]53[[:space:]]|[.]53[[:space:]])' | head -8 || true
echo '=== Memory budget and OOM evidence (check timestamps) ==='
sysctl vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_page_size 2>/dev/null || true
swapinfo -h 2>/dev/null || true
ps axo pid,rss,pcpu,command | sort -nr -k2 | head -15 || true
dmesg -a 2>/dev/null | grep -Ei 'failed to reclaim|out of swap|killed.*(unbound|php|netstat)|memory allocation failure' | tail -22 || true
echo '=== pfBlockerNG process overlap and historical DNSBL update markers ==='
ps axo pid,rss,pcpu,command | grep -E '[p]fblockerng.php|[p]hp_pfb|[p]fb_unbound' | head -10 || true
for file in /var/log/pfblockerng/pfblockerng.log /var/log/pfblockerng/pfblockerng.log.0; do
  if [ -r "$file" ]; then
    echo 'pfblockerng_log_present=yes'
    # Deliberately omit arbitrary domain lists, URLs, block reports and secrets.
    grep -Ei 'UPDATE PROCESS ENDED|DNSBL.*PASSED|DNSBL.*FAILED|Restarting DNSBL Service|Downloading.*IPinfo|pfb.*out of memory' "$file" 2>/dev/null | tail -18 || true
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
    sed -E 's#(python-script:).*#\\1 [configured]#' | head -12 || true
fi
echo '=== pfBlockerNG DNSBL input size (top 10 feed files only) ==='
if [ -d /var/db/pfblockerng/dnsblorig ]; then
  # Use file metadata; never read or print filter entries.
  for f in /var/db/pfblockerng/dnsblorig/*; do
    [ -f "$f" ] || continue
    case "$f" in *.md5|*.raw|*.sha*) continue ;; esac
    size=$(stat -f %z "$f" 2>/dev/null || echo 0)
    printf '%s %s\\n' "$size" "$(basename "$f")"
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
