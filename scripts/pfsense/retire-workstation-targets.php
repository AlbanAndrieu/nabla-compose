<?php
// Retire the pfSense targets that still aim at the workstation 172.17.0.57.
// Run from the workstation, check first, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/retire-workstation-targets.php
// Runbook: docs/runbooks/2026-11-14-pfsense-stale-workstation-targets.md
require_once('config.inc');
require_once('util.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
require_once('itemid.inc');
require_once('firewall_nat.inc');
require_once('haproxy/haproxy.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const WS = '172.17.0.57';
// Pools of retired services, deleted whole. Do not repoint them: TrueNAS :3000 is Langfuse, :9000 ClickHouse.
const RETIRED_POOLS = ['ntopng', 'graylog'];
// pool, server, port: the services moved to TrueNAS or were stopped. Since 15/11 the workstation
// Apache (:8082) is published only by the workstation Cloudflare tunnel, behind Access.
const STALE_SERVERS = [
    ['albandrieu-apache-login-honeypot', 'albandrieu', '3000'],
    ['albandrieu-apache', 'albandrieu', '8082'],
    ['nabla-index', 'famp', '8082'],
    ['prod_front', 'apache', '8082'],
    // Pools no frontend uses, so never generated: inactive keeps the "nothing to .57" check true.
    ['nexus', 'nexus', '8081'],
    ['vault', 'vault', '8200'],
];
const STALE_FRONTEND = 'login';
const STALE_NAT_DESCR = 'albandrieu nexus 8081';

// Any frontend field equal to the pool name counts as a use: a false match only blocks the delete.
function uses_pool($value, string $pool): bool
{
    return is_array($value) ? (bool)array_filter($value, fn($v) => uses_pool($v, $pool)) : $value === $pool;
}

$ha_changed = false;
$found = 0;

$pools = config_get_path('installedpackages/haproxy/ha_pools/item', []);
$frontends = config_get_path('installedpackages/haproxy/ha_backends/item', []);
$drop_pools = [];
foreach (RETIRED_POOLS as $name) {
    $pi = array_search($name, array_map(fn($p) => $p['name'] ?? '', $pools), true);
    if ($pi === false) {
        print("OK: haproxy pool {$name} absent\n");
        continue;
    }
    $active = array_filter($pools[$pi]['ha_servers']['item'] ?? [], fn($s) => ($s['status'] ?? '') !== 'inactive');
    $users = array_column(array_filter($frontends, fn($f) => uses_pool($f, $name)), 'name');
    if ($active || $users) {
        fwrite(STDERR, sprintf("ERROR: haproxy pool %s has %d active server(s) and is used by [%s]; nothing written\n",
            $name, count($active), implode(',', $users)));
        exit(1);
    }
    printf("CHANGE: haproxy pool %s (%d inactive server(s), no frontend) to delete\n", $name, count($pools[$pi]['ha_servers']['item'] ?? []));
    $drop_pools[] = $pi;
}

foreach ($pools as $pi => $pool) {
    foreach ($pool['ha_servers']['item'] ?? [] as $si => $srv) {
        foreach (STALE_SERVERS as [$p, $n, $port]) {
            if (($pool['name'] ?? '') !== $p || ($srv['name'] ?? '') !== $n
                || ($srv['address'] ?? '') !== WS || ($srv['port'] ?? '') !== $port) {
                continue;
            }
            $found++;
            $st = $srv['status'] ?? '';
            printf("%s: haproxy pool %s server %s %s:%s status=%s\n", $st === 'inactive' ? 'OK' : 'CHANGE', $p, $n, WS, $port, $st);
            if ($st !== 'inactive' && $apply) {
                config_set_path("installedpackages/haproxy/ha_pools/item/{$pi}/ha_servers/item/{$si}/status", 'inactive');
                $ha_changed = true;
            }
        }
    }
}

foreach ($frontends as $fi => $fe) {
    if (($fe['name'] ?? '') !== STALE_FRONTEND) {
        continue;
    }
    $found++;
    $st = $fe['status'] ?? '';
    printf("%s: haproxy frontend %s status=%s\n", $st === 'disabled' ? 'OK' : 'CHANGE', STALE_FRONTEND, $st);
    if ($st !== 'disabled' && $apply) {
        config_set_path("installedpackages/haproxy/ha_backends/item/{$fi}/status", 'disabled');
        $ha_changed = true;
    }
}

$nat_ids = [];
foreach (config_get_path('nat/rule', []) as $ni => $rule) {
    if (($rule['descr'] ?? '') === STALE_NAT_DESCR && ($rule['interface'] ?? '') === 'wan'
        && ($rule['local-port'] ?? '') === '8081') {
        $nat_ids[] = $ni;
        printf("CHANGE: nat rdr #%d %s -> %s:%s (associated filter rule %s)\n", $ni, STALE_NAT_DESCR,
            $rule['target'] ?? '', $rule['local-port'], $rule['associated-rule-id'] ?? '-');
    }
}
if (!$nat_ids) {
    print("OK: nat rdr " . STALE_NAT_DESCR . " absent\n");
}

printf("summary: %d haproxy object(s) matched, %d pool(s) to delete, %d nat rule(s) to remove, mode=%s\n",
    $found, count($drop_pools), count($nat_ids), $apply ? 'apply' : 'check');
if ($found !== count(STALE_SERVERS) + 1) {
    fwrite(STDERR, "ERROR: expected " . (count(STALE_SERVERS) + 1) . " haproxy objects; config drifted, nothing written\n");
    exit(1);
}
if (!$apply) {
    exit(0);
}

if ($drop_pools) {
    // Re-read: the loops above may have changed server status in the same array.
    $kept = array_diff_key(config_get_path('installedpackages/haproxy/ha_pools/item', []), array_flip($drop_pools));
    config_set_path('installedpackages/haproxy/ha_pools/item', array_values($kept));
    $ha_changed = true;
}
$changes = [];
if ($nat_ids) {
    remove_rdr_rules($nat_ids, $changes);
}
if (!$ha_changed && !isset($changes['rdr_rules'])) {
    print("OK: nothing to change\n");
    exit(0);
}

write_config('nabla: retire stale workstation 172.17.0.57 targets (HAProxy ntopng/graylog, login, Apache 8082, NAT 8081)');

if ($ha_changed) {
    $messages = '';
    if (!haproxy_check_and_run($messages, true)) {
        fwrite(STDERR, "ERROR: haproxy reload failed: {$messages}\n");
        exit(1);
    }
    unlink_if_exists($d_haproxyconfdirty_path);
    print("OK: haproxy reloaded\n");
}
if (isset($changes['rdr_rules'])) {
    // filter_configure() only queues the reload and returns nothing; check with `pfctl -sn` afterwards.
    filter_configure();
    clear_subsystem_dirty('natconf');
    clear_subsystem_dirty('filter');
    print("OK: filter reload queued\n");
}
