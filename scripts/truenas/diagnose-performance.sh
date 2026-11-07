#!/usr/bin/env bash
set -euo pipefail

# Shared compact/full diagnostic bootstrap.
NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/diagnostic.sh
source "$(dirname -- "${NABLA_SCRIPT_DIR}")/lib/diagnostic.sh"
nabla_diagnostic_maybe_wrap "${BASH_SOURCE[0]}" "$@"

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
  # Volume scans took over 5 minutes on a busy raidz2 pool; keep the report bounded.
  timeout 60 docker system df || printf 'docker system df unavailable or over 60s (rc=%s)\n' "$?"

  printf '\n-- container anomalies --\n'
  docker ps -q |
    xargs -r timeout 60 docker inspect --format '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}} mem_limit={{.HostConfig.Memory}}' |
    awk '
      /health=unhealthy/ || $3 !~ /restarts=0$/ { print }
      / mem_limit=0$/ { unlimited++ }
      END { printf "running containers without memory limit: %d\n", unlimited }
    ' || true
  # An OOM-killed JVM can stay <defunct> while its container still reports Up.
  printf 'defunct processes: '
  pgrep -c -r Z || true
  # Zombies pile up under container init processes that never reap healthcheck children.
  # Resolve each parent's container from its cgroup ID against one docker ps listing,
  # so the fix (init: true) targets the right service without per-PID docker calls.
  container_names="$(docker ps --no-trunc --format '{{.ID}} {{.Names}}' 2>/dev/null || true)"
  printf 'top zombie parents (count ppid parent zombie container):\n'
  ps -eo ppid=,stat=,comm= | awk '$2 ~ /^Z/ { print $1, $3 }' | sort | uniq -c | sort -rn | head -10 |
    while read -r count ppid child; do
      container_id="$(grep -oE '[0-9a-f]{64}' "/proc/${ppid}/cgroup" 2>/dev/null | head -1 || true)"
      container="$(awk -v id="${container_id}" 'id != "" && $1 == id { print $2; exit }' <<<"${container_names}")"
      printf '  %s %s %s %s %s\n' "${count}" "${ppid}" \
        "$(ps -o comm= -p "${ppid}" 2>/dev/null)" "${child}" "${container:-host}"
    done
  # cgroup v2 memory.peak is the high-water mark since container start: size
  # mem_limit from it rather than from one docker stats sample.
  printf 'container memory peak, top 20 (peak_MiB current_MiB limit name):\n'
  while read -r id name; do
    [[ -n "${id}" ]] || continue
    for dir in "/sys/fs/cgroup/docker/${id}" "/sys/fs/cgroup/system.slice/docker-${id}.scope"; do
      [[ -r "${dir}/memory.peak" ]] || continue
      printf '%s %s %s %s\n' "$(($(<"${dir}/memory.peak") / 1048576))" \
        "$(($(<"${dir}/memory.current") / 1048576))" "$(<"${dir}/memory.max")" "${name}"
      break
    done
  done <<<"${container_names}" | sort -rn | head -20 | sed 's/^/  /'
  # A zombie that keeps live threads is stuck in the kernel with SIGKILL pending
  # (2026-11-04: wazuh-indexer JVM). Its containerd shim then holds the container
  # lock, so docker inspect and TrueNAS app.query hang; only a reboot frees it.
  printf 'zombies with live threads (pid threads elapsed command):\n'
  ps -eo pid=,stat=,nlwp=,etime=,comm= | awk '$2 ~ /^Z/ && $3 > 1 { print "  " $1, $3, $4, $5 }'
  printf 'containers whose inspect exceeds 5s (stuck lock):\n'
  docker ps -aq | while read -r id; do
    timeout 5 docker inspect --format '{{.Name}}' "${id}" >/dev/null 2>&1 || printf '  %s\n' "${id}"
  done
  # containerd logged "too many open files" while container starts hung.
  # Only resolve its PID once; do not enumerate /proc for a missing process.
  containerd_pid="$(pgrep -o -x containerd 2>/dev/null || true)"
  if [[ -n "${containerd_pid}" && -d "/proc/${containerd_pid}/fd" ]]; then
    printf 'containerd open fds: %s (limit %s)\n' \
      "$(find "/proc/${containerd_pid}/fd" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" \
      "$(awk '/Max open files/ { print $4; exit }' "/proc/${containerd_pid}/limits" 2>/dev/null)"
  else
    printf 'containerd open fds: unavailable (process not found)\n'
  fi
else
  printf 'docker unavailable\n'
fi

section "TrueNAS app states"
if have midclt && have jq; then
  # app.query may be expensive under TrueNAS pressure. Collect metadata once,
  # then render both views from the already sanitized tabular projection.
  if app_rows="$(midclt call app.query | jq -r '
    .[]
    | [.id, .state, ((.active_workloads.containers // 0) | tostring)]
    | @tsv
  ')"; then
    printf '%s\n' "${app_rows}" | sed '/^$/d' | sort -k2,2 -k1,1 || true
    printf '\n-- non-running apps --\n'
    printf '%s\n' "${app_rows}" | awk -F '\t' 'NF >= 2 && $2 != "RUNNING"' || true
  else
    printf 'TrueNAS app inventory unavailable\n'
  fi
fi

section "Pool health and I/O"
if have zpool; then
  zpool status -x || true
  zpool list || true
  printf '\n-- cpool I/O sample --\n'
  zpool iostat -v cpool 1 3 || true
  printf '\n-- snapshot count --\n'
  zfs list -H -t snapshot -o name 2>/dev/null | wc -l || true
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
