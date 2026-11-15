#!/usr/bin/env bash
# pfSense emergency access: direct LAN SSH, bounded probes, explicit service restarts.
set -euo pipefail
mode="--check"
target="${PFSENSE_SSH_TARGET:-admin@172.17.0.1}"
port="${PFSENSE_SSH_PORT:-9922}"
usage() {
  cat <<'USAGE'
Usage: bash scripts/pfsense/recover-access.sh [--check|--dns|--ui|--all] [--target USER@HOST] [--port PORT]
  --check  Read-only fast diagnostics (default).
  --dns    Restart Unbound only.
  --ui     Restart PHP-FPM and WebConfigurator only.
  --all    Restart Unbound, PHP-FPM and WebConfigurator.
Defaults: admin@172.17.0.1:9922. No DNS or pfREST API required.
USAGE
}
while (($#)); do
  case "$1" in
    --check|--dns|--ui|--all) mode="$1"; shift ;;
    --target) (($# >= 2)) || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) (($# >= 2)) || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unsupported option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$target" =~ ^[a-zA-Z0-9._@-]+$ ]] || { echo "ERROR: invalid target" >&2; exit 2; }
[[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port > 0 && 10#$port <= 65535)) || {
  echo "ERROR: invalid port" >&2; exit 2;
}
opts=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5
      -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -p "$port")
dns_from_workstation() {
  local resolver="$1" protocol="$2" output
  local -a args=(-4 +time=2 +tries=1)
  if ! command -v dig >/dev/null 2>&1; then
    echo "WARN: workstation dig unavailable"; return 2
  fi
  [[ "$protocol" != tcp ]] || args+=(+tcp)
  if output="$(dig "${args[@]}" "@${resolver}" example.com A 2>&1)" &&
     [[ "$output" == *"status: NOERROR"* ]]; then
    echo "PASS: workstation_dns_${protocol}_${resolver}=NOERROR"; return 0
  fi
  echo "WARN: workstation_dns_${protocol}_${resolver}=FAILED"; return 1
}
ui_from_workstation() {
  if ! command -v curl >/dev/null 2>&1; then return 0; fi
  local code
  # A one-off bypass of TLS name verification, for trusted private-IP probing only.
  code="$(curl -k -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 6 \
    https://172.17.0.1:10443/ 2>/dev/null)" || code=000
  if [[ "$code" != 000 ]]; then
    echo "PASS: lan_gui_http=${code} (not proof of authenticated login)"
  else
    echo "WARN: lan_gui_http=UNREACHABLE"
  fi
}
echo "pfSense quick recovery mode=${mode} target=${target}:${port}"
if [[ "$mode" == "--check" ]]; then
  echo "==> Workstation DNS path"
  dns_from_workstation 172.17.0.1 udp || true
  dns_from_workstation 172.17.0.1 tcp || true
  dns_from_workstation 9.9.9.9 udp || true
fi

echo "==> Direct SSH diagnostic / explicit service recovery"
ssh_rc=0
ssh "${opts[@]}" "$target" /bin/sh -s -- "$mode" <<'REMOTE' || ssh_rc=$?
set -u
mode="$1"
fail=0
dns_query() {
  label="$1"; server="$2"
  if ! command -v drill >/dev/null 2>&1; then
    echo "WARN: ${label}=DRILL_UNAVAILABLE"; return 2
  fi
  reply="$(drill -t A example.com "@${server}" 2>&1)" || reply=""
  if printf '%s\n' "$reply" | grep -q 'rcode: NOERROR'; then
    echo "PASS: ${label}=NOERROR"; return 0
  fi
  echo "WARN: ${label}=FAILED_OR_SERVFAIL"; return 1
}
status_report() {
  echo "==> Process and resources"
  uptime
  if pgrep -x unbound >/dev/null 2>&1; then
    echo "PASS: unbound_process=RUNNING"
  else
    echo "WARN: unbound_process=MISSING"
  fi
  if unbound-control -c /var/unbound/unbound.conf status 2>/dev/null |
      grep -q 'is running'; then
    echo "PASS: unbound_control=RUNNING"
  else
    echo "WARN: unbound_control=UNAVAILABLE"
  fi
  echo "==> Unbound generated config sanity (no mutation)"
  if command -v unbound-checkconf >/dev/null 2>&1; then
    check_rc=0
    check_output="$(unbound-checkconf /var/unbound/unbound.conf 2>&1)" || check_rc=$?
    printf '%s\n' "$check_output" | tail -n 8
    if [ "$check_rc" -eq 0 ]; then
      echo "PASS: unbound_checkconf=VALID"
    else
      echo "WARN: unbound_checkconf=INVALID exit=$check_rc"
    fi
  else
    echo "WARN: unbound_checkconf=NOT_INSTALLED"
  fi
  echo "==> Effective port, interfaces, ACLs and transports"
  if [ -r /var/unbound/unbound.conf ]; then
    grep -E '^[[:space:]]*(interface:|port:|access-control:|do-ip4:|do-udp:|do-tcp:|outgoing-interface:)' \
      /var/unbound/unbound.conf | head -n 45 || true
  fi
  echo "==> DNS IPv4 listeners"
  sockstat -4 -l 2>/dev/null |
    awk 'NR > 1 && $6 ~ /:53$/ { print; seen=1 } END { if (!seen) print "WARN: dns_ipv4_listener=MISSING" }'
  if [ "$mode" = "--check" ]; then
    echo "==> Real DNS lookups (recursive / upstream)"
    dns_query dns_loopback 127.0.0.1 || true
    dns_query dns_lan_ip 172.17.0.1 || true
    dns_query public_dns_egress 9.9.9.9 || true
  else
    echo "INFO: DNS deep probes skipped in recovery mode for faster restart"
  fi
  if [ -S /var/run/php-fpm.socket ]; then
    echo "PASS: php_fpm_socket=PRESENT"
  else
    echo "WARN: php_fpm_socket=MISSING"
  fi
  if [ -r /var/log/system.log ]; then
    echo "==> Recent Unbound / memory failures (bounded)"
    grep -Ei 'unbound.*(killed|fatal|error|failed|stopp)|failed to reclaim|out of memory|out of swap' \
      /var/log/system.log 2>/dev/null | tail -8 || true
  fi
}
status_report
if [ "$mode" != "--check" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: root-equivalent pfSense SSH admin required for service restart"
    exit 77
  fi
  if [ "$mode" = "--dns" ] || [ "$mode" = "--all" ]; then
    echo "==> Restart Unbound only"
    if [ -x /usr/local/sbin/pfSsh.php ]; then
      /usr/local/sbin/pfSsh.php playback svc restart unbound || fail=1
    elif [ -x /etc/rc.d/unbound ]; then
      /etc/rc.d/unbound restart || fail=1
    else
      echo "ERROR: no supported Unbound restart command"; fail=1
    fi
  fi
  if [ "$mode" = "--ui" ] || [ "$mode" = "--all" ]; then
    echo "==> Restart PHP-FPM"
    /etc/rc.php-fpm_restart || fail=1
    echo "==> Restart WebConfigurator"
    /etc/rc.restart_webgui || fail=1
  fi
  echo "==> Verify post-restart status"
  status_report
  if [ "$mode" = "--dns" ] || [ "$mode" = "--all" ]; then
    dns_query dns_loopback_post 127.0.0.1 || fail=1
  fi
else
  echo "result=CHECK_ONLY_NO_MUTATION"
fi
exit "$fail"
REMOTE
if ((ssh_rc)); then
  echo "ERROR: SSH diagnostic/recovery failed (exit=${ssh_rc}); no successful recovery is claimed" >&2
  exit "$ssh_rc"
fi
echo "==> Workstation post-check"
if [[ "$mode" == "--dns" || "$mode" == "--all" ]]; then
  dns_from_workstation 172.17.0.1 udp || {
    echo "ERROR: LAN DNS still unavailable; inspect Unbound listener, ACL, PF, upstream recursion" >&2
    exit 1
  }
  dns_from_workstation 172.17.0.1 tcp || true
fi
ui_from_workstation
echo "result=SSH_${mode}_COMPLETE (evaluate PASS/WARN lines before declaring recovery)"
