#!/usr/bin/env bash
# Read-only pfSense memory and pflow evidence; no service restarts or secrets.
set -euo pipefail
target="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
port="${PFSENSE_SSH_PORT:-}"
usage() { echo "usage: $0 --check [--target SSH_ALIAS] [--port PORT]" >&2; }
[[ "${1:-}" == "--check" ]] || { usage; exit 2; }
shift
while (($#)); do
  case "$1" in
    --target) [[ $# -ge 2 ]] || { usage; exit 2; }; target="$2"; shift 2 ;;
    --port) [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || { usage; exit 2; }; port="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
opts=(-o BatchMode=yes -o ConnectTimeout=8)
[[ -z "${port}" ]] || opts+=(-p "${port}")
echo "Read-only pfSense memory/pflow audit target=${target}"
ssh "${opts[@]}" "${target}" '/bin/sh -s' <<'REMOTE'
set -u
echo '==> Timestamp and uptime'
date; uptime
echo '==> Memory / swap'
sysctl hw.physmem vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count vm.stats.vm.v_cache_count vm.stats.vm.v_page_size 2>/dev/null || true
swapinfo -h 2>/dev/null || true
free_pages=$(sysctl -n vm.stats.vm.v_free_count 2>/dev/null || echo 0)
inactive_pages=$(sysctl -n vm.stats.vm.v_inactive_count 2>/dev/null || echo 0)
page_size=$(sysctl -n vm.stats.vm.v_page_size 2>/dev/null || echo 4096)
case "$free_pages:$inactive_pages:$page_size" in
  *[!0-9:]*|'') echo 'WARN: cannot calculate available memory' ;;
  *) echo "Estimated free+inactive KiB: $(( (free_pages + inactive_pages) * page_size / 1024 ))" ;;
esac
echo '==> Largest resident processes (KiB)'
ps axo pid,rss,pcpu,command | sort -nr -k2 | head -18 || true
echo '==> pfBlockerNG cron pressure (read-only)'
cron_lines=$(ps axo pid,rss,pcpu,command 2>/dev/null | grep '[p]fblockerng.php cron' || true)
if [ -n "$cron_lines" ]; then
  echo 'WARN: pfBlockerNG cron is active; defer pflow activation and DNSBL rebuild'
  printf '%s\n' "$cron_lines"
else
  echo 'PASS: no pfBlockerNG cron process observed'
fi
echo '==> pfBlockerNG DNSBL helper processes'
ps axo pid,rss,pcpu,command 2>/dev/null | grep -E '[a]wk .*pfbtemp|[a]wk .*pfblockerng/dnsbl' | head -8 || true
echo '==> Unbound health and memory'
unbound-control -c /var/unbound/unbound.conf status 2>&1 || true
unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | grep -E '^(mem[.]|total[.]num[.]queries|total[.]num[.]recursivereplies)' | head -22 || true
echo '==> Recent kernel memory failures (historical evidence; check timestamps)'
dmesg | grep -Ei 'failed to reclaim|out of swap|killed.*(unbound|php|netstat)' | tail -20 || true
echo '==> pfSense kernel and pflow module availability'
uname -a
kldstat 2>/dev/null | grep -E '(^Id|pflow)' || true
for module in /boot/kernel/pflow.ko /boot/modules/pflow.ko; do
  [ ! -f "$module" ] || ls -l "$module"
done
command -v pflowctl || true
echo '==> pflow boot references (file names and matching lines only)'
for config in /boot/loader.conf /boot/loader.conf.local /etc/rc.conf /etc/rc.conf.local; do
  [ ! -r "$config" ] || grep -Hni 'pflow' "$config" || true
done
echo '==> pflow XML paths (read-only, names only; values never printed)'
if command -v php >/dev/null 2>&1; then
  php -r '
    $xml = @simplexml_load_file("/conf/config.xml");
    if ($xml === false) { fwrite(STDERR, "WARN: pfSense config unavailable\n"); exit(0); }
    $nodes = $xml->xpath("//*[local-name()=\"pflow\"]");
    echo "pflow leaf count: ", count($nodes), "\n";
    foreach ($nodes as $node) {
      $path = [];
      $dom = dom_import_simplexml($node);
      while ($dom && $dom->nodeType === XML_ELEMENT_NODE) {
        array_unshift($path, $dom->nodeName);
        $dom = $dom->parentNode;
      }
      echo "/", implode("/", $path), " [", trim((string)$node) === "" ? "empty" : "populated", "]\n";
    }
  ' 2>&1 || true
fi
echo '==> pflowctl status (nonzero is diagnostic, not a script failure)'
pflowctl -v -l 2>&1 || true
echo '==> pflow interfaces and sockets'
ifconfig -l | tr ' ' '\n' | grep '^pflow' || true
sockstat -4 -l 2>/dev/null | grep -Ei 'pflow|2055' || true
echo '==> pflow runtime configuration (redacted: no config.xml dump)'
for iface in $(ifconfig -l | tr ' ' '\n' | grep '^pflow'); do
  ifconfig "$iface" 2>/dev/null | grep -E '(^pflow|pflow:|src |dst |version|domain|status)' || true
done
echo '==> DNS regression smoke'
for name in defectdojo.int.albandrieu.com s3.int.albandrieu.com; do
  drill "$name" @127.0.0.1 2>/dev/null | grep -E 'rcode:|IN[[:space:]]+A[[:space:]]' | head -4 || true
done
REMOTE
