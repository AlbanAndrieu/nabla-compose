<?php
// Homarr answers the default HAProxy backend prod_back while Heimdall is down (backup server).
// Run from the workstation, check first, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/prod-back-homarr-fallback.php
require_once('config.inc');
require_once('util.inc');
require_once('haproxy/haproxy.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const POOL = 'prod_back';
// Heimdall answers /tag/nabla with 302 but Homarr with 404: a backup failing its check is never used.
const CHECK_URI = '/';
const BACKUP = ['name' => 'homarr', 'address' => '172.17.0.24', 'port' => '30100', 'status' => 'backup'];

$pools = config_get_path('installedpackages/haproxy/ha_pools/item', []);
$pi = array_search(POOL, array_map(fn($p) => $p['name'] ?? '', $pools), true);
if ($pi === false) {
    fwrite(STDERR, "ERROR: haproxy pool " . POOL . " absent; nothing written\n");
    exit(1);
}
$base = "installedpackages/haproxy/ha_pools/item/{$pi}";
$changes = 0;

$uri = (string)($pools[$pi]['monitor_uri'] ?? '');
printf("%s: %s monitor_uri=%s expected=%s\n", $uri === CHECK_URI ? 'OK' : 'CHANGE', POOL, $uri, CHECK_URI);
if ($uri !== CHECK_URI) {
    $changes++;
    config_set_path("{$base}/monitor_uri", CHECK_URI);
}

$servers = is_array($pools[$pi]['ha_servers']['item'] ?? null) ? $pools[$pi]['ha_servers']['item'] : [];
$si = array_search(BACKUP['name'], array_map(fn($s) => $s['name'] ?? '', $servers), true);
$current = $si === false ? [] : array_intersect_key($servers[$si], BACKUP);
$ok = $current == BACKUP;
printf("%s: %s server %s %s:%s status=%s expected=backup\n", $ok ? 'OK' : 'CHANGE', POOL, BACKUP['name'],
    BACKUP['address'], BACKUP['port'], $current['status'] ?? 'absent');
if (!$ok) {
    $changes++;
    $servers[$si === false ? count($servers) : $si] = array_merge($si === false ? [] : $servers[$si], BACKUP);
    config_set_path("{$base}/ha_servers/item", array_values($servers));
}

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || $changes === 0) {
    exit(0);
}

// Same server id assignment as a pool save in the GUI.
config_id();
write_config('nabla: Homarr backup server for HAProxy prod_back (Heimdall down)');
$messages = '';
if (!haproxy_check_and_run($messages, true)) {
    fwrite(STDERR, "ERROR: haproxy reload failed: {$messages}\n");
    exit(1);
}
unlink_if_exists($d_haproxyconfdirty_path);
print("OK: haproxy reloaded\n");
