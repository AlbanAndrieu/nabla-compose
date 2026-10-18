#!/usr/bin/env bash
# Read-only pfSense Unbound split-zone and memory incident evidence, via SSH.
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
args=(-o BatchMode=yes -o ConnectTimeout=8)
[[ -z "$port" ]] || args+=(-p "$port")
echo "==> SSH read-only Unbound audit target=$target port=${port:-ssh-config/default}"
# No secrets/config.xml dumps; remote shell is pfSense tcsh, invoke sh explicitly.
ssh "${args[@]}" "$target" '/bin/sh -s' <<'REMOTE'
set -u
echo '==> Unbound status'
unbound-control -c /var/unbound/unbound.conf status 2>&1 || true
echo '==> Effective split-zone directives (no secret-bearing config.xml dump)'
grep -nE 'int[.]albandrieu[.]com|172[.]17[.]0[.]24|forward-zone|forward-addr|domain-insecure|private-domain' /var/unbound/unbound.conf || echo 'WARN: no matching effective forward directives'
echo '==> Forwarding lookup'
unbound-control -c /var/unbound/unbound.conf lookup defectdojo.int.albandrieu.com 2>&1 | head -30 || true
echo '==> Kernel memory reclaim evidence'
dmesg | grep -Ei 'unbound|killed|failed to reclaim|out of swap' | tail -40 || true
echo '==> Memory top processes'
ps axo pid,rss,vsz,pcpu,pmem,command | sort -nr -k2 | head -12 || true
echo '==> Resolver memory counters'
unbound-control -c /var/unbound/unbound.conf stats_noreset 2>/dev/null | grep '^mem[.]' | head -15 || true
REMOTE
