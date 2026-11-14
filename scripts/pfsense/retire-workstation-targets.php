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
// pool, server, port: the services moved to TrueNAS or were stopped.
const STALE_SERVERS = [
    ['ntopng', 'ntopng', '3000'],
    ['graylog', 'graylog', '9000'],
    ['albandrieu-apache-login-honeypot', 'albandrieu', '3000'],
];
const STALE_FRONTEND = 'login';
const STALE_NAT_DESCR = 'albandrieu nexus 8081';

$ha_changed = false;
$found = 0;

foreach (config_get_path('installedpackages/haproxy/ha_pools/item', []) as $pi => $pool) {
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

foreach (config_get_path('installedpackages/haproxy/ha_backends/item', []) as $fi => $fe) {
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

printf("summary: %d haproxy object(s) matched, %d nat rule(s) to remove, mode=%s\n", $found, count($nat_ids), $apply ? 'apply' : 'check');
if ($found !== count(STALE_SERVERS) + 1) {
    fwrite(STDERR, "ERROR: expected " . (count(STALE_SERVERS) + 1) . " haproxy objects; config drifted, nothing written\n");
    exit(1);
}
if (!$apply) {
    exit(0);
}

$changes = [];
if ($nat_ids) {
    remove_rdr_rules($nat_ids, $changes);
}
if (!$ha_changed && !isset($changes['rdr_rules'])) {
    print("OK: nothing to change\n");
    exit(0);
}

write_config('nabla: retire stale workstation 172.17.0.57 targets (HAProxy ntopng/graylog/login, NAT 8081)');

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
    if (filter_configure() !== 0) {
        fwrite(STDERR, "ERROR: filter reload failed\n");
        exit(1);
    }
    clear_subsystem_dirty('natconf');
    clear_subsystem_dirty('filter');
    print("OK: filter reloaded\n");
}
