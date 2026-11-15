#!/usr/bin/env bash
# Idempotent private split-DNS repair; target is LAN SSH, not public HAProxy.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mode="check"
target="${PFSENSE_SSH_TARGET:-admin@172.17.0.1}"
port="${PFSENSE_SSH_PORT:-9922}"
usage() {
  cat <<'USAGE'
Usage: bash scripts/pfsense/reconcile-split-dns.sh [--check|--apply] [--target USER@HOST] [--port PORT]
  --check  Read-only pfSense config drift plus optional DNS queries (default).
  --apply  Restore ONLY int.albandrieu.com -> 172.17.0.24 and outgoing=All.
            Native config history, restart Unbound if changed, then DNS smoke.
No global PF flush, boot change, package install or DNSBL reload.
USAGE
}
while (($#)); do
  case "$1" in
    --check) mode="check"; shift ;;
    --apply) mode="apply"; shift ;;
    --target) (($#>=2)) || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) (($#>=2)) || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "${target}" =~ ^[A-Za-z0-9._@-]+$ ]] || { echo "ERROR: invalid SSH target" >&2; exit 2; }
if ! [[ "${port}" =~ ^[0-9]{1,5}$ ]] || ((10#${port} < 1 || 10#${port} > 65535)); then
  echo "ERROR: invalid SSH port" >&2; exit 2
fi
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8
          -o ServerAliveInterval=5 -o ServerAliveCountMax=2 -p "${port}")
php_script="${script_dir}/manage-split-dns.php"
[[ -r "${php_script}" ]] || { echo "ERROR: missing PHP payload" >&2; exit 2; }
echo "pfSense private-DNS mode=${mode} SSH=${target}:${port}"
if [[ "${mode}" == "apply" ]]; then
  # Fail closed if the authoritative LAN DNS server cannot answer the expected name.
  command -v dig >/dev/null || { echo "ERROR: dig is required for apply preflight" >&2; exit 2; }
  answer="$(dig -4 +short +time=2 +tries=1 @172.17.0.24 sample.int.albandrieu.com A)" || {
    echo "ERROR: Pi-hole 172.17.0.24 did not respond; no configuration change" >&2; exit 3;
  }
  if ! grep -qx '172.17.0.24' <<< "${answer}"; then
    echo "ERROR: Pi-hole returned an unexpected private A record; no configuration change" >&2
    exit 3
  fi
  echo "PASS: Pi-hole direct authoritative name preflight"
fi

# The PHP payload is not copied to the appliance. Its only mutable path is apply.
remote_output="$(ssh "${ssh_opts[@]}" "${target}" env "NABLA_SPLIT_DNS_ACTION=${mode}" \
  /usr/local/bin/php < "${php_script}")" || {
  echo "ERROR: SSH/PHP config audit failed; no service restart attempted" >&2; exit 1;
}
printf '%s\n' "${remote_output}"
if [[ "${mode}" == "check" ]]; then
  live_status=0
  if command -v dig >/dev/null 2>&1; then
    echo "==> Live DNS check (Pi-hole then pfSense)"
    for dns in 172.17.0.24 172.17.0.1; do
      result="$(dig -4 +short +time=2 +tries=1 "@${dns}" sample.int.albandrieu.com A)" || result=""
      if grep -qx '172.17.0.24' <<< "${result}"; then
        echo "PASS: private_dns_${dns}=172.17.0.24"
      else
        echo "DRIFT: private_dns_${dns}=UNRESOLVED_OR_WRONG"
        live_status=2
      fi
    done
  else
    echo "WARN: live DNS test unavailable (dig not installed)"
    live_status=3
  fi
  if grep -q '^DRIFT:' <<< "${remote_output}" || ((live_status == 2)); then
    echo "result=SPLIT_DNS_DRIFT"
    exit 2
  fi
  if ((live_status == 3)); then
    echo "result=SPLIT_DNS_LIVE_UNVERIFIED"
    exit 3
  fi
  echo "result=SPLIT_DNS_CONFIG_CONVERGED"
  exit 0
fi

if grep -q '^result=APPLY_CHANGED_RESTART_REQUIRED$' <<< "${remote_output}"; then
  echo "==> Restart Unbound using native pfSense service management"
  ssh "${ssh_opts[@]}" "${target}" /usr/local/sbin/pfSsh.php playback svc restart unbound
else
  echo "INFO: no configuration change; no restart"
fi
if ! command -v dig >/dev/null 2>&1; then
  echo "WARN: dig unavailable; live DNS not verified"
  exit 2
fi
public="$(dig -4 +short +time=2 +tries=1 @172.17.0.1 example.com A)" || public=""
private="$(dig -4 +short +time=2 +tries=1 @172.17.0.1 sample.int.albandrieu.com A)" || private=""
if grep -qx '172.17.0.24' <<< "${private}" && [[ -n "${public}" ]]; then
  echo "PASS: private split-DNS=172.17.0.24; public DNS also answered"
  echo "result=APPLY_VERIFIED"
  exit 0
fi
echo "ERROR: config applied or already converged, but DNS smoke failed" >&2
echo "INFO: review unbound-control list_forwards, DNS Resolver logs, and Boot Environment" >&2
exit 1
