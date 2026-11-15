<?php
// Native pflow export to Akvorado on TrueNAS: one NetFlow v5 exporter, domain 1, LAN source, every
// rule tracked by default. It lives in config.xml, so the 2026-11-15 boot environment fallback lost it.
// No Cloudflare (domain 2) exporter while the 1 GB Netgate 1100 is memory constrained.
// Run from the workstation, check first, then apply (check-drift.sh runs the check):
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/reconcile-pflow.php
require_once('config.inc');
require_once('util.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const NABLA_EXPORTER = [
    'enable' => '', 'src' => 'lan', 'srcport' => '', 'dst' => '172.17.0.24', 'dstport' => '2055',
    'proto' => '5', 'domain' => '1', 'descr' => 'Akvorado TrueNAS',
];
const NABLA_COMPARED = ['enable', 'src', 'dst', 'dstport', 'proto', 'domain'];
const NABLA_RUNTIME = '/version 5 domain 1 src 172[.]17[.]0[.]1 dst 172[.]17[.]0[.]24:2055/';
// pflow.ko held with ~217 MiB free on 2026-10-18; below this the appliance is already near OOM.
const NABLA_MIN_FREE_MB = 150;

function nabla_runtime_ok(): bool
{
    exec('/sbin/pflowctl -v -l 2>/dev/null', $out);
    return (bool)preg_match(NABLA_RUNTIME, implode("\n", $out));
}

$pflow = config_get_path('pflow', []);
$changes = 0;
foreach (['enable', 'default'] as $key) {
    $on = is_array($pflow) && array_key_exists($key, $pflow);
    printf("%s: pflow %s=%s expected=on\n", $on ? 'OK' : 'CHANGE', $key, $on ? 'on' : 'off');
    $changes += $on ? 0 : 1;
}
$exporters = is_array($pflow['exporters'] ?? null) ? $pflow['exporters'] : [];
$want = array_intersect_key(NABLA_EXPORTER, array_flip(NABLA_COMPARED));
$same = count($exporters) === 1 && is_array(current($exporters))
    && array_intersect_key(current($exporters), $want) == $want;
printf("%s: exporters=%d expected=1 (v5 domain 1 lan -> 172.17.0.24:2055)\n", $same ? 'OK' : 'CHANGE', count($exporters));
$changes += $same ? 0 : 1;

$runtime = nabla_runtime_ok();
printf("%s: runtime pflowctl exporter=%s\n", $runtime ? 'OK' : ($changes ? 'INFO' : 'WARN'), $runtime ? 'present' : 'absent');
exec('/sbin/sysctl -n vm.stats.vm.v_free_count vm.stats.vm.v_inactive_count hw.pagesize 2>/dev/null', $mem);
$free_mb = count($mem) === 3 ? intdiv(((int)$mem[0] + (int)$mem[1]) * (int)$mem[2], 1048576) : 0;
printf("INFO: free+inactive=%d MiB (apply needs %d)\n", $free_mb, NABLA_MIN_FREE_MB);

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || ($changes === 0 && $runtime)) {
    exit(0);
}
if ($free_mb < NABLA_MIN_FREE_MB) {
    fwrite(STDERR, "ERROR: free+inactive {$free_mb} MiB < " . NABLA_MIN_FREE_MB . " MiB; nothing written\n");
    exit(1);
}

if ($changes) {
    config_set_path('pflow/enable', '');
    config_set_path('pflow/default', '');
    config_set_path('pflow/exporters', [uniqid('pflow') => NABLA_EXPORTER]);
    write_config('nabla: native pflow NetFlow v5 export to Akvorado TrueNAS 172.17.0.24:2055');
}
// Loads pflow.ko, recreates the exporters, then queues a filter reload for "set state-defaults pflow".
filter_pflow_configure();
if (!nabla_runtime_ok()) {
    fwrite(STDERR, "ERROR: pflowctl shows no matching exporter after apply\n");
    exit(1);
}
print("OK: pflow exporter configured; filter reload queued\n");
