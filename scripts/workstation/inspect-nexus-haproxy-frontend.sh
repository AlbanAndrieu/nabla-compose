#!/usr/bin/env bash
# Read-only pfSense HAProxy ACL inspection from workstation.
# Supports offline --fixture for hermetic tests. No pfSense mutation.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
AWK_SOURCE="${ROOT}/scripts/pfsense/inspect-nexus-haproxy-frontend.awk"
FRONTEND="main_Web_HTTPS"
BACKEND=""
FIXTURE=""

usage() {
  cat <<'EOF'
Usage: bash scripts/workstation/inspect-nexus-haproxy-frontend.sh [--frontend NAME] [--backend NAME] [--fixture PATH]

Read-only audit of the pfSense HAProxy frontend main_Web_HTTPS via
workstation SSH. The old fWeb_HTTPS name is NOT used by default.
--frontend NAME  Explicit override for a verified frontend.
--backend NAME   Show only named backend server targets (address:port; no options).
--fixture PATH   Offline fixture; does not connect to pfSense.

Reports only selected ACL/routing directives, never certificates, full
backend sections or request-header values. Review metadata before sharing.
EOF
}
while (($#)); do
  case "$1" in
    --frontend)
      (($# >= 2)) || { printf 'ERROR: missing --frontend value\n' >&2; exit 2; }
      FRONTEND="$2"; shift 2 ;;
    --backend)
      (($# >= 2)) || { printf 'ERROR: missing --backend value\n' >&2; exit 2; }
      BACKEND="$2"; shift 2 ;;
    --fixture)
      (($# >= 2)) || { printf 'ERROR: missing --fixture value\n' >&2; exit 2; }
      FIXTURE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unexpected argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
# Allowlist protects the remote shell argument from injection.
[[ "$FRONTEND" =~ ^[a-zA-Z][a-zA-Z0-9_.-]*$ ]] || {
  printf 'ERROR: invalid HAProxy frontend name\n' >&2; exit 2;
}
if [[ -n "$BACKEND" ]] && [[ ! "$BACKEND" =~ ^[a-zA-Z][a-zA-Z0-9_.-]*$ ]]; then
  printf 'ERROR: invalid HAProxy backend name\n' >&2
  exit 2
fi
[[ -f "$AWK_SOURCE" ]] || { printf 'ERROR: AWK source missing\n' >&2; exit 2; }
if [[ -n "$FIXTURE" ]]; then
  [[ -r "$FIXTURE" ]] || { printf 'ERROR: fixture missing or unreadable\n' >&2; exit 2; }
  exec awk -v "frontend=$FRONTEND" -v "backend_name=$BACKEND" -f "$AWK_SOURCE" "$FIXTURE"
fi

SSH_TARGET="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
SSH_PORT="${PFSENSE_SSH_PORT:-}"
[[ "$SSH_TARGET" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$ ]] || {
  printf 'ERROR: invalid SSH target\n' >&2; exit 2;
}
SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=1)
if [[ -n "$SSH_PORT" ]]; then
  [[ "$SSH_PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$SSH_PORT > 0 && 10#$SSH_PORT <= 65535)) || {
    printf 'ERROR: invalid SSH port\n' >&2; exit 2;
  }
  SSH_ARGS+=(-p "$SSH_PORT")
fi
command -v ssh >/dev/null || { printf 'ERROR: ssh is unavailable\n' >&2; exit 2; }
# Portable awk program is read from stdin (-f -). The frontend value is
# validated above; the generated pfSense HAProxy config is read, not changed.
ssh "${SSH_ARGS[@]}" "$SSH_TARGET" \
  "awk -v frontend=$FRONTEND -v backend_name=$BACKEND -f - /var/etc/haproxy/haproxy.cfg" < "$AWK_SOURCE"
