#!/usr/bin/env bash
# Read-only pfSense Plus upgrade inventory from the workstation.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/pfsense/console.sh
source "${SCRIPT_DIR}/console.sh"

usage() {
  cat <<'EOF'
Usage: prepare-upgrade.sh --ssh TARGET [--port PORT]

Collect a read-only pre-upgrade inventory from pfSense. This command never
backs up config.xml, removes packages, runs pfSense-upgrade, or reboots.

Options:
  --ssh TARGET   SSH config alias or user@host (required)
  --port PORT    Optional SSH port; omitted ports use the SSH config/default
  -h, --help     Show this help
EOF
}

target=""
port=""
while (($#)); do
  case "$1" in
    --ssh)
      (($# >= 2)) || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    --port)
      (($# >= 2)) || { usage >&2; exit 2; }
      port="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$target" ]] || { usage >&2; exit 2; }
if [[ -n "$port" && ! "$port" =~ ^[0-9]{1,5}$ ]] ||
   [[ -n "$port" && "$port" -gt 65535 ]]; then
  printf 'ERROR: --port must be an integer from 1 to 65535\n' >&2
  exit 2
fi

ssh_options=(-o BatchMode=yes -o ConnectTimeout=10)
[[ -z "$port" ]] || ssh_options+=(-p "$port")

pfsense_ui_banner "upgrade preflight · read-only · target 26.07-RELEASE"
ssh "${ssh_options[@]}" "$target" /bin/sh -s <<'REMOTE' | pfsense_ui_render
set -u

section() { printf '\n=== %s ===\n' "$1"; }
section 'Identity and release'
printf 'version='
if [ -r /etc/version ]; then cat /etc/version; else echo unavailable; fi
printf 'architecture='
uname -m 2>/dev/null || echo unavailable
printf 'model='
sysctl -n hw.model 2>/dev/null || echo unavailable

section 'Memory and storage'
sysctl hw.physmem vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count hw.pagesize 2>/dev/null || true
df -h / /conf 2>/dev/null || true
if command -v bectl >/dev/null 2>&1; then
  section 'ZFS boot environments'
  bectl list 2>&1 || true
elif command -v beadm >/dev/null 2>&1; then
  section 'ZFS boot environments'
  beadm list 2>&1 || true
else
  section 'Boot environment tooling'
  echo 'No bectl/beadm found; verify filesystem and recovery path in the GUI.'
fi

section 'Installed packages (inventory only)'
if command -v pkg >/dev/null 2>&1; then
  pkg info 2>&1 || true
  section 'REST API package'
  pkg info -x 'pfSense-pkg-RESTAPI' 2>&1 || echo 'pfSense-pkg-RESTAPI not found'
else
  echo 'pkg command unavailable'
fi

section 'Upgrade boundary'
echo 'This report is read-only. It did not export config.xml, change packages, update pfSense, or reboot.'
REMOTE
