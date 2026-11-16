<?php
// Unrouted hosts of the WAN frontends get the Project Honey Pot App instead of the Heimdall login
// (decision of 16/11, roadmap H07b step 2). Deploy apps/honeypot first, then check, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/haproxy-honeypot-default.php
require_once('config.inc');
require_once('util.inc');
require_once('haproxy/haproxy.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const FRONTENDS = ['Web_HTTPS', 'freenas', 'Web_HTTPS-8082'];
// Only / and the script report a visitor to Project Honey Pot: probe the static /healthz.
const POOL = ['name' => 'honeypot', 'check_type' => 'HTTP', 'monitor_uri' => '/healthz', 'httpcheck_method' => 'GET',
    'monitor_agentport' => 'honeypot'];
const SERVER = ['name' => 'honeypot', 'address' => '172.17.0.24', 'port' => '31090', 'status' => 'active'];
// A new pool clones this one, so every field a GUI save writes exists (PHP 8 warns on missing keys).
const TEMPLATE = 'prod_back';

function items($node): array
{
    return is_array($node['item'] ?? null) ? $node['item'] : [];
}

$frontends = config_get_path('installedpackages/haproxy/ha_backends/item', []);
$fe_index = array_flip(array_map(fn($f) => $f['name'] ?? '', $frontends));
$missing = array_diff(FRONTENDS, array_keys($fe_index));
$pools = config_get_path('installedpackages/haproxy/ha_pools/item', []);
$names = array_map(fn($p) => $p['name'] ?? '', $pools);
$pi = array_search(POOL['name'], $names, true);
$ti = array_search(TEMPLATE, $names, true);
if ($missing || ($pi === false && $ti === false)) {
    fwrite(STDERR, sprintf("ERROR: frontend(s) %s or pool %s absent; nothing written\n",
        implode(',', $missing) ?: '-', TEMPLATE));
    exit(1);
}

$changes = 0;
$pool = $pi === false ? $pools[$ti] : $pools[$pi];
$servers = $pi === false ? [] : items($pool['ha_servers'] ?? []);
$si = array_search(SERVER['name'], array_map(fn($s) => $s['name'] ?? '', $servers), true);
$pool_ok = $pi !== false && array_intersect_key($pool, POOL) == POOL;
$server_ok = $si !== false && array_intersect_key($servers[$si], SERVER) == SERVER;
printf("%s: pool %s check=%s %s %s\n", $pool_ok ? 'OK' : 'CHANGE', POOL['name'], $pi === false ? 'absent' : ($pool['check_type'] ?? ''),
    $pool['httpcheck_method'] ?? '', $pool['monitor_uri'] ?? '');
printf("%s: pool %s server %s:%s status=%s\n", $server_ok ? 'OK' : 'CHANGE', POOL['name'], SERVER['address'], SERVER['port'],
    $si === false ? 'absent' : ($servers[$si]['status'] ?? ''));
if (!$pool_ok || !$server_ok) {
    $changes++;
    if ($pi === false) {
        unset($pool['id']);
    }
    $servers[$si === false ? count($servers) : $si] = array_merge($si === false ? [] : $servers[$si], SERVER);
    $pool = array_merge($pool, POOL, ['ha_servers' => ['item' => array_values($servers)]]);
    $pools[$pi === false ? count($pools) : $pi] = $pool;
    config_set_path('installedpackages/haproxy/ha_pools/item', array_values($pools));
}

foreach (FRONTENDS as $name) {
    $fi = $fe_index[$name];
    $fe = $frontends[$fi];
    // The honeypot logs the visitor from X-Forwarded-For, trusted only from the pfSense LAN address.
    $ok = ($fe['backend_serverpool'] ?? '') === POOL['name'] && ($fe['forwardfor'] ?? '') === 'yes';
    printf("%s: frontend %s default=%s forwardfor=%s expected=%s+yes\n", $ok ? 'OK' : 'CHANGE', $name,
        $fe['backend_serverpool'] ?? '', $fe['forwardfor'] ?? '', POOL['name']);
    if (!$ok) {
        $changes++;
        config_set_path("installedpackages/haproxy/ha_backends/item/{$fi}/backend_serverpool", POOL['name']);
        config_set_path("installedpackages/haproxy/ha_backends/item/{$fi}/forwardfor", 'yes');
    }
}

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || $changes === 0) {
    exit(0);
}

// Same pool and server id assignment as a pool save in the GUI.
config_id();
write_config('nabla: honeypot as default HAProxy backend of the WAN frontends');
$messages = '';
if (!haproxy_check_and_run($messages, true)) {
    fwrite(STDERR, "ERROR: haproxy reload failed: {$messages}\n");
    exit(1);
}
unlink_if_exists($d_haproxyconfdirty_path);
print("OK: haproxy reloaded\n");
