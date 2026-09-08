#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}"     "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

section() {
  printf '\n===== %s =====\n' "$1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

section "Host"
date --iso-8601=seconds
hostname
uname -a
uptime
cat /proc/loadavg 2>/dev/null || true

section "Pressure stall information"
for resource in cpu memory io; do
  if [[ -r "/proc/pressure/${resource}" ]]; then
    printf '%s:\n' "${resource}"
    cat "/proc/pressure/${resource}"
  fi
done

section "Memory and swap"
free -h || true
if have swapon; then
  swapon --show || true
fi

section "ZFS ARC"
arcstats=/proc/spl/kstat/zfs/arcstats
if [[ -r "${arcstats}" ]]; then
  awk '
    $1 ~ /^(size|c|c_min|c_max|hits|misses|memory_throttle_count)$/ {
      printf "%-24s %s\n", $1, $3
    }
  ' "${arcstats}"
else
  printf 'ARC stats unavailable\n'
fi

section "vmstat sample"
if have vmstat; then
  vmstat 1 5
else
  printf 'vmstat unavailable\n'
fi

section "Top CPU processes"
ps axo pid,ppid,stat,etime,pcpu,pmem,rss,vsz,comm,args   --sort=-pcpu |
head -30 || true

section "Top RSS processes"
ps axo pid,ppid,stat,etime,pcpu,pmem,rss,vsz,comm,args   --sort=-rss |
head -30 || true

section "Docker runtime summary"
if have docker; then
  docker ps -a     --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true

  printf '\n-- docker stats --\n'
  docker stats --no-stream     --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.BlockIO}}\t{{.PIDs}}' || true

  printf '\n-- docker disk usage --\n'
  docker system df || true
else
  printf 'docker unavailable\n'
fi

section "TrueNAS app states"
if have midclt && have jq; then
  midclt call app.query |
  jq -r '
    .[]
    | [
        .id,
        .state,
        ((.active_workloads.containers // 0) | tostring)
      ]
    | @tsv
  ' |
  sort -k2,2 -k1,1 || true

  printf '\n-- non-running apps --\n'
  midclt call app.query |
  jq -r '
    .[]
    | select(.state != "RUNNING")
    | [
        .id,
        .state,
        ((.active_workloads.containers // 0) | tostring)
      ]
    | @tsv
  ' || true
fi

section "Pool health and I/O"
if have zpool; then
  zpool status -x || true
  zpool list || true
  printf '\n-- cpool I/O sample --\n'
  zpool iostat -v cpool 1 3 || true
else
  printf 'zpool unavailable\n'
fi

section "Filesystem capacity"
df -hT /mnt/cpool 2>/dev/null || df -hT || true
df -ih /mnt/cpool 2>/dev/null || df -ih || true

section "Network socket summary"
if have ss; then
  ss -s || true
fi

section "Recent kernel pressure / I/O events"
if have journalctl; then
  journalctl -k -b --no-pager 2>/dev/null |
    grep -Ei       'oom|out of memory|memory cgroup|blocked for more than|hung task|I/O error|nvme.*error|ata.*error|reset controller' |
    tail -100 || true
else
  dmesg 2>/dev/null |
    grep -Ei       'oom|out of memory|memory cgroup|blocked for more than|hung task|I/O error|nvme.*error|ata.*error|reset controller' |
    tail -100 || true
fi

section "Interpretation hints"
cat <<'EOF'
- sustained memory PSI or swap activity: investigate memory pressure before restarting more apps;
- sustained I/O PSI plus high zpool latency: investigate storage saturation or a busy dataset/container;
- one container dominating CPU/RSS/BlockIO: inspect that service before broad redeploys;
- many DEPLOYING/CRASHED apps: stop repeated lifecycle retries and repair deterministic Compose errors first;
- kernel OOM/hung-task/I/O events: treat as a platform incident, not an application-only failure.
EOF
