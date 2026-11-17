<?php
// Stop the RRD collector (updaterrd.sh rewrites every /var/db/rrd/*.rrd each minute) to cut the
// steady write load on the failing Netgate 1100 eMMC (no RAM disk). Netgate lists "disable RRD
// graphs" in Troubleshooting Disk Writes. Graphs stay available remotely: Prometheus
// pfsense_exporter, Zabbix and Loki. Incident: docs/pfsense/incidents/2026-11-17-pfsense-userland-freeze.md
// Not chosen: "disable local logging" also skips system_sshguard_start() (syslog.inc), which would
// unprotect the WAN-exposed SSH; /var RAM disks need more than the ~290 MB free seen on 17/11.
// Run from the workstation, check first:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/disable-rrd-graphing.php
// then "php -- apply", then check again. "php -- revert" turns graphing back on (SSD hardware).
require_once('config.inc');
require_once('rrd.inc');

$mode = $argv[1] ?? 'check';
if (!in_array($mode, ['check', 'apply', 'revert'], true)) {
    print("ERROR: mode must be check, apply or revert\n");
    exit(2);
}
$want = $mode === 'revert';
$enabled = config_path_enabled('rrd');
// enable_rrd_graphing() starts or kills the collector through this pid file. Tests override it.
$running = isvalidpid(getenv('NABLA_RRD_PIDFILE') ?: '/var/run/updaterrd.sh.pid');

$state = $enabled ? 'enabled' : 'disabled';
print($enabled === $want ? "OK: RRD graphing is {$state} in config.xml\n" : "CHANGE: RRD graphing is {$state} in config.xml\n");
if ($running !== $want) {
    printf("%s: RRD collector is %s\n", $enabled === $want ? 'WARN' : 'INFO', $running ? 'running' : 'stopped');
}
$changes = (int)($enabled !== $want) + (int)($enabled === $want && $running !== $want);
printf("summary: %d change(s), mode=%s\n", $changes, $mode);
if ($mode === 'check' || $changes === 0) {
    exit(0);
}
if ($enabled !== $want) {
    $rrd = config_get_path('rrd', []);
    if ($want) {
        $rrd['enable'] = '';
    } else {
        unset($rrd['enable']);
    }
    config_set_path('rrd', $rrd);
    write_config($want ? 'nabla: re-enable RRD graphing' : 'nabla: disable RRD graphing (eMMC wear, incident 2026-11-17)');
}
enable_rrd_graphing();
print($want ? "OK: RRD graphing enabled, collector started\n" : "OK: RRD graphing disabled, collector stopped\n");
