#!/usr/bin/env bash
# Read-only host/container resource diagnostics for TrueNAS and Linux.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

MODE="${1:---all}"
case "${MODE}" in
  --all|--host|--docker|-h|--help) ;;
  *) printf 'Usage: %s [--all|--host|--docker]\n' "$0" >&2; exit 2 ;;
esac
if [[ "${MODE}" == "-h" || "${MODE}" == "--help" ]]; then
  printf 'Read-only host and Docker resource inventory; no restarts, secrets or config changes.\n'
  exit 0
fi

section() { diag_section '' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }

if [[ "${MODE}" == "--all" || "${MODE}" == "--host" ]]; then
  section "Host identity / uptime"
  hostname 2>/dev/null || true
  uname -a 2>/dev/null || true
  uptime 2>/dev/null || true
  section "Memory"
  if has free; then free -h; else head -n 8 /proc/meminfo; fi
  section "CPU consumers"
  ps -eo pid,ppid,user,comm,%cpu,%mem,rss,etime --sort=-%cpu | head -n 21 || true
  section "RSS consumers"
  ps -eo pid,ppid,user,comm,%cpu,%mem,rss,etime --sort=-rss | head -n 21 || true
  section "QEMU/VMs: scoped process identifiers (no command-line arguments)"
  ps -eo pid,ppid,user,comm,rss,etime | awk 'NR == 1 || /qemu-system/'
  if has virsh; then
    # TrueNAS may run QEMU without a default libvirt socket; failure is advisory.
    virsh -c qemu:///system list --all 2>&1 || printf 'INFO: libvirt system socket unavailable; inspect TrueNAS VM API/UI.\n'
  fi
  section "Filesystems"
  if has df; then df -hT -x tmpfs -x devtmpfs 2>/dev/null | head -n 25; fi
fi

if [[ "${MODE}" == "--all" || "${MODE}" == "--docker" ]]; then
  section "Docker status"
  if ! has docker; then
    printf 'INFO: Docker CLI unavailable.\n'
  elif ! docker info >/dev/null 2>&1; then
    printf 'INFO: Docker daemon unavailable or permission denied.\n'
  else
    docker info --format 'Containers={{.Containers}} Running={{.ContainersRunning}} Paused={{.ContainersPaused}} Stopped={{.ContainersStopped}} Images={{.Images}}'
    section "Docker statistics (single snapshot)"
    docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}' 2>&1 | head -n 40 || true
    section "Container status"
    docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | head -n 60 || true
  fi
fi
section "Safety"
diag_info 'Read-only inventory. Process command lines, container env, secrets and logs are not printed.'
