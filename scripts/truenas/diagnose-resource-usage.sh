#!/usr/bin/env bash
# Read-only resource inventory for Linux workstation or TrueNAS.
set -uo pipefail
MODE="${1:---all}"
case "$MODE" in
  --all|--docker|--host|-h|--help) ;;
  *) echo "Usage: bash $0 [--all|--docker|--host]" >&2; exit 2 ;;
esac
if [[ "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  echo "Read-only CPU/memory/disk/container inventory. No restart or config changes."
  exit 0
fi
section() { printf '\n==> %s\n' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }

if [[ "$MODE" == "--all" || "$MODE" == "--host" ]]; then
  section "Host identity"
  hostname 2>/dev/null || true
  uname -a 2>/dev/null || true
  section "Load and uptime"
  uptime 2>/dev/null || true
  section "Memory"
  if has free; then free -h; elif [[ -r /proc/meminfo ]]; then head -n 8 /proc/meminfo; else echo "memory summary unavailable"; fi
  section "Top processes by CPU"
  if has ps; then ps -eo pid,ppid,user,comm,%cpu,%mem,rss --sort=-%cpu | head -n 16; fi
  section "Top processes by resident memory"
  if has ps; then ps -eo pid,ppid,user,comm,%cpu,%mem,rss --sort=-rss | head -n 16; fi
  section "Filesystem usage"
  if has df; then df -hT -x tmpfs -x devtmpfs 2>/dev/null | head -n 25; fi
fi

if [[ "$MODE" == "--all" || "$MODE" == "--docker" ]]; then
  section "Docker daemon"
  if ! has docker; then
    echo "Docker CLI unavailable in this environment (expected on workstation or some TrueNAS contexts)."
  elif ! docker info >/dev/null 2>&1; then
    echo "Docker daemon unavailable or permission denied; rerun with sudo if appropriate."
  else
    docker info --format 'Containers={{.Containers}} Running={{.ContainersRunning}} Paused={{.ContainersPaused}} Stopped={{.ContainersStopped}} Images={{.Images}}'
    section "Container CPU/memory/network/block I/O (one snapshot)"
    docker stats --no-stream --format 'table {{.Name}}\t{{.ID}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}' 2>&1 | head -n 35
    section "Container restart/status inventory"
    docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}' | head -n 45
  fi
fi
section "Safety"
echo "Read-only inventory; no credentials, environment variables, logs, or container config are printed."
