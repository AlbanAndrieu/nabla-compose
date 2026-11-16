<?php
// Delete the HAProxy use_backend rules whose pool has no active or backup server, then the
// frontend ACLs no remaining rule uses. A dead default backend is only reported.
// Run after retire-workstation-targets.php, check first, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/prune-dead-haproxy-routes.php
require_once('config.inc');
require_once('util.inc');
require_once('haproxy/haproxy.inc');

$apply = ($argv[1] ?? 'check') === 'apply';

function items($node): array
{
    return is_array($node['item'] ?? null) ? $node['item'] : [];
}

$live = [];
foreach (config_get_path('installedpackages/haproxy/ha_pools/item', []) as $pool) {
    $live[$pool['name'] ?? ''] = (bool)array_filter(items($pool['ha_servers'] ?? []),
        fn($s) => in_array($s['status'] ?? 'active', ['active', 'backup'], true));
}

$changes = 0;
foreach (config_get_path('installedpackages/haproxy/ha_backends/item', []) as $fi => $fe) {
    $name = $fe['name'] ?? '';
    if (($fe['status'] ?? '') !== 'active') {
        continue;
    }
    $default = $fe['backend_serverpool'] ?? '';
    if ($default !== '' && empty($live[$default])) {
        printf("WARN: frontend %s default backend %s has no active server (not changed)\n", $name, $default);
    }
    $kept = [];
    foreach (items($fe['a_actionitems'] ?? []) as $action) {
        $pool = $action['use_backendbackend'] ?? '';
        if (($action['action'] ?? '') === 'use_backend' && empty($live[$pool])) {
            printf("CHANGE: frontend %s rule use_backend %s if %s (no active server)\n", $name, $pool, $action['acl'] ?? '');
            $changes++;
            continue;
        }
        $kept[] = $action;
    }
    // A rule condition can combine several ACLs ("bababou || famp", "!login").
    $used = [];
    foreach ($kept as $action) {
        preg_match_all('/[A-Za-z0-9_.-]+/', (string)($action['acl'] ?? ''), $m);
        $used += array_flip($m[0]);
    }
    $acls = [];
    foreach (items($fe['ha_acls'] ?? []) as $acl) {
        if (isset($used[$acl['name'] ?? ''])) {
            $acls[] = $acl;
            continue;
        }
        printf("CHANGE: frontend %s acl %s (%s %s) used by no rule\n", $name, $acl['name'] ?? '', $acl['expression'] ?? '', $acl['value'] ?? '');
        $changes++;
    }
    if (count($kept) !== count(items($fe['a_actionitems'] ?? [])) || count($acls) !== count(items($fe['ha_acls'] ?? []))) {
        $base = "installedpackages/haproxy/ha_backends/item/{$fi}";
        config_set_path("{$base}/a_actionitems", ['item' => $kept]);
        config_set_path("{$base}/ha_acls", ['item' => $acls]);
    }
}

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || $changes === 0) {
    exit(0);
}

write_config('nabla: prune HAProxy rules and ACLs of pools without active servers');
$messages = '';
if (!haproxy_check_and_run($messages, true)) {
    fwrite(STDERR, "ERROR: haproxy reload failed: {$messages}\n");
    exit(1);
}
unlink_if_exists($d_haproxyconfdirty_path);
print("OK: haproxy reloaded\n");
