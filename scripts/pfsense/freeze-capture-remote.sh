#!/bin/sh
# Read-only snapshots streamed by freeze-capture.sh over SSH (pfSense /bin/sh, no bashisms).
# Writes nothing on pfSense and never calls logger: everything goes to stdout only.
# Each command is bounded by timeout so one stuck process cannot stall the whole loop.
rounds="${1:-180}"
# eMMC wear, read once (Netgate disk-lifetime doc): LIFE A/B 0x01..0x0b = 10 % steps, PRE_EOL 0x01 normal, 0x02 warning, 0x03 urgent.
echo "=== eMMC health"
if command -v mmc; then
  timeout 10 mmc extcsd read /dev/mmcsd0rpmb | grep -E 'LIFE|EOL'
else
  echo "mmc-utils absent (pkg install mmc-utils writes to the failing pool: install only on operator decision)"
fi
i=0
while [ "${i}" -lt "${rounds}" ]; do
  echo "=== $(date '+%F %T') round ${i} $(uptime)"
  timeout 10 ps -axo pid,ppid,state,wchan,%cpu,rss,etime,command | head -80
  for name in syslogd sshd sshguard filterlog php_pfb tail_pfb kea-dhcp4 nginx php-fpm zabbix_agentd unbound; do
    pids="$(pgrep -x "${name}" | tr '\n' ' ')"
    if [ -n "${pids}" ]; then
      echo "--- procstat ${name}"
      # shellcheck disable=SC2086 # pids is a space-separated list on purpose.
      timeout 10 procstat -kk ${pids}
    fi
  done
  echo "--- /var/run/log queues"
  timeout 10 netstat -f unix -n | grep -E 'Recv-Q|/var/run/log'
  echo "--- memory and eMMC"
  timeout 10 sysctl vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count kstat.zfs.misc.arcstats.size
  timeout 10 iostat -x -w 1 -c 2 mmcsd0 | tail -2
  echo "--- dmesg"
  timeout 10 dmesg | tail -15
  i=$((i + 1))
  sleep 5
done
