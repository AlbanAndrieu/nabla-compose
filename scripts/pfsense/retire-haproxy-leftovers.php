<?php
// Retire the HAProxy leftovers the operator listed on 16/11: the dead pools nexus, vault,
// albandrieu-apache (workstation, retired by retire-workstation-targets.php) and clamav-openvas,
// the disabled LAMP/FAMP servers of prod_front, and the public :8082 frontend, which only ever
// served the workstation Apache. Run from the workstation, check first, then apply, then
// prune-dead-haproxy-routes.php for the ACLs left without a rule:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/retire-haproxy-leftovers.php
require_once('config.inc');
require_once('util.inc');
require_once('functions.inc');
require_once('haproxy/haproxy.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const DROP_POOLS = ['nexus', 'vault', 'albandrieu-apache', 'clamav-openvas'];
const DROP_SERVERS = ['prod_front' => ['lamp', 'famp']];
const DISABLE_FRONTENDS = ['Web_HTTPS-8082'];

$pools = config_get_path('installedpackages/haproxy/ha_pools/item', []);
$frontends = config_get_path('installedpackages/haproxy/ha_backends/item', []);
$changes = 0;

foreach ($frontends as $fi => $fe) {
    $name = $fe['name'] ?? '';
    // A default backend cannot simply vanish: stop rather than leave the frontend dangling.
    if (in_array($fe['backend_serverpool'] ?? '', DROP_POOLS, true)) {
        fwrite(STDERR, "ERROR: frontend {$name} defaults to pool {$fe['backend_serverpool']}; nothing written\n");
        exit(1);
    }
    if (in_array($name, DISABLE_FRONTENDS, true)) {
        $st = $fe['status'] ?? '';
        printf("%s: haproxy frontend %s status=%s\n", $st === 'disabled' ? 'OK' : 'CHANGE', $name, $st);
        if ($st !== 'disabled') {
            $frontends[$fi]['status'] = 'disabled';
            $changes++;
        }
    }
    $rules = $fe['a_actionitems']['item'] ?? [];
    foreach ($rules as $ri => $rule) {
        if (($rule['action'] ?? '') === 'use_backend' && in_array($rule['use_backendbackend'] ?? '', DROP_POOLS, true)) {
            printf("CHANGE: frontend %s rule use_backend %s if %s\n", $name, $rule['use_backendbackend'], $rule['acl'] ?? '');
            unset($rules[$ri]);
            $changes++;
        }
    }
    if (isset($fe['a_actionitems']['item'])) {
        $frontends[$fi]['a_actionitems']['item'] = array_values($rules);
    }
}

foreach ($pools as $pi => $pool) {
    $name = $pool['name'] ?? '';
    if (in_array($name, DROP_POOLS, true)) {
        printf("CHANGE: haproxy pool %s (%d server(s)) to delete\n", $name, count($pool['ha_servers']['item'] ?? []));
        unset($pools[$pi]);
        $changes++;
        continue;
    }
    $servers = $pool['ha_servers']['item'] ?? [];
    foreach ($servers as $si => $server) {
        if (in_array($server['name'] ?? '', DROP_SERVERS[$name] ?? [], true)) {
            printf("CHANGE: haproxy pool %s server %s %s:%s status=%s\n", $name, $server['name'],
                $server['address'] ?? '', $server['port'] ?? '', $server['status'] ?? '');
            unset($servers[$si]);
            $changes++;
        }
    }
    if (isset($pool['ha_servers']['item'])) {
        $pools[$pi]['ha_servers']['item'] = array_values($servers);
    }
}

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || $changes === 0) {
    exit(0);
}
config_set_path('installedpackages/haproxy/ha_pools/item', array_values($pools));
config_set_path('installedpackages/haproxy/ha_backends/item', $frontends);
write_config('nabla: retire HAProxy leftovers (nexus, vault, albandrieu-apache, clamav-openvas, LAMP/FAMP, :8082)');
$messages = '';
if (!haproxy_check_and_run($messages, true)) {
    fwrite(STDERR, "ERROR: haproxy reload failed: {$messages}\n");
    exit(1);
}
unlink_if_exists($d_haproxyconfdirty_path);
print("OK: haproxy reloaded\n");
