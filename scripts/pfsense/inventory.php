<?php
// Read-only inventory of what pfSense does, for the Freebox switch and the decommissioning study
// (docs/pfsense/decommission-study.md). Prints stable JSON: sorted, no timestamp, so two runs on an
// unchanged box are identical. Never prints MAC addresses, alias contents, keys or passwords.
//   ssh -p 9922 admin@172.17.0.1 "php" < scripts/pfsense/inventory.php > logs/pfsense-inventory-$(date +%F).json
// The output names LAN hosts and devices: keep it under logs/ (gitignored), not in the public repo.
require_once('config.inc');

$get = fn($path, $default = []) => config_get_path($path, $default);
$on = fn($node, $key = 'enable') => is_array($node) && array_key_exists($key, $node);
$words = fn($s) => array_values(array_filter(preg_split('/\s+/', trim((string)$s)), 'strlen'));

$aliases = [];
foreach ($get('aliases/alias') as $a) {
    $aliases[$a['name']] = $a;
}
// Alias references (names only): rules, NAT, packages and other aliases.
$refs = [];
$scan = function ($node, $where) use (&$scan, &$refs, $aliases) {
    if (is_array($node)) {
        foreach ($node as $v) {
            $scan($v, $where);
        }
        return;
    }
    foreach (preg_split('/[\s,]+/', (string)$node) as $tok) {
        if (isset($aliases[$tok])) {
            $refs[$tok][$where] = true;
        }
    }
};
$scan($get('filter/rule'), 'filter');
$scan($get('nat/rule'), 'nat');
$scan($get('installedpackages/haproxy'), 'haproxy');
$scan($get('installedpackages/pfblockerng'), 'pfblockerng');
foreach ($aliases as $name => $a) {
    $scan($a['address'] ?? '', "alias:{$name}");
}

$inv = ['interfaces' => [], 'dhcp' => [], 'nat_forwards' => [], 'aliases' => [], 'filter' => [], 'dns' => [],
        'haproxy' => [], 'acme' => [], 'vpn' => [], 'services' => []];
foreach ($get('interfaces') as $name => $i) {
    $inv['interfaces'][$name] = ['descr' => $i['descr'] ?? '', 'if' => $i['if'] ?? '', 'ipv4' => trim(($i['ipaddr'] ?? '') . '/' . ($i['subnet'] ?? ''), '/'),
                                 'ipv6' => $i['ipaddrv6'] ?? '', 'enabled' => $on($i)];
}
foreach ($get('dhcpd') as $name => $d) {
    $maps = [];
    foreach ($d['staticmap'] ?? [] as $m) {
        $maps[] = ['ip' => $m['ipaddr'] ?? '', 'hostname' => $m['hostname'] ?? '', 'descr' => $m['descr'] ?? '', 'has_mac' => !empty($m['mac'])];
    }
    usort($maps, fn($x, $y) => ip2long($x['ip'] ?: '0.0.0.0') <=> ip2long($y['ip'] ?: '0.0.0.0'));
    $inv['dhcp'][$name] = ['enabled' => $on($d), 'range' => ($d['range']['from'] ?? '') . '-' . ($d['range']['to'] ?? ''),
                           'dns' => array_values((array)($d['dnsserver'] ?? [])), 'static_maps' => $maps];
}
$inv['dhcp']['_backend'] = $get('dhcpbackend', 'isc');

$pass = [];
foreach ($get('filter/rule') as $f) {
    if (isset($f['associated-rule-id'])) {
        $pass[$f['associated-rule-id']] = isset($f['disabled']) ? 'disabled' : 'enabled';
    }
}
foreach ($get('nat/rule') as $r) {
    $target = $r['target'] ?? '';
    $ips = isset($aliases[$target]) ? array_values(array_filter($words($aliases[$target]['address'] ?? ''), fn($x) => filter_var($x, FILTER_VALIDATE_IP))) : [$target];
    $inv['nat_forwards'][] = ['interface' => $r['interface'] ?? '', 'proto' => $r['protocol'] ?? '', 'port' => $r['destination']['port'] ?? '',
                              'target' => $target, 'target_ips' => $ips, 'local_port' => $r['local-port'] ?? '',
                              'nat' => isset($r['disabled']) ? 'disabled' : 'enabled',
                              'pass_rule' => $pass[$r['associated-rule-id'] ?? ''] ?? (($r['associated-rule-id'] ?? '') === 'pass' ? 'nat-pass' : 'none'),
                              'descr' => $r['descr'] ?? ''];
}
foreach ($aliases as $name => $a) {
    // Entry count only: some aliases hold third-party addresses.
    $inv['aliases'][$name] = ['type' => $a['type'] ?? '', 'entries' => count($words($a['address'] ?? $a['url'] ?? '')),
                              'used_by' => array_keys($refs[$name] ?? [])];
}
foreach ($get('filter/rule') as $f) {
    $key = ($f['interface'] ?? '?') . (isset($f['disabled']) ? ':disabled' : ':enabled');
    $inv['filter'][$key] = ($inv['filter'][$key] ?? 0) + 1;
}
$u = $get('unbound');
$inv['dns'] = ['resolver' => $on($u) ? 'unbound' : 'off', 'dnssec' => $on($u, 'dnssec'), 'host_overrides' => count($u['hosts'] ?? []),
               'domain_overrides' => array_map(fn($d) => ($d['domain'] ?? '') . ' -> ' . ($d['ip'] ?? ''), $u['domainoverrides'] ?? []),
               'register_dhcp' => $on($u, 'regdhcp'), 'system_domain' => $get('system/domain', ''),
               'upstreams' => array_values((array)$get('system/dnsserver'))];
foreach ($get('installedpackages/haproxy/ha_backends/item') as $fe) {
    $binds = array_map(fn($b) => ($b['extaddr'] ?? '?') . ':' . ($b['extaddr_port'] ?? '?'), $fe['a_extaddr']['item'] ?? []);
    $inv['haproxy'][] = ['frontend' => $fe['name'] ?? '', 'status' => $fe['status'] ?? '', 'binds' => $binds,
                         'backends' => count($fe['ha_actions']['item'] ?? []) + (empty($fe['backend_serverpool']) ? 0 : 1)];
}
foreach ($get('installedpackages/acme/certificates/item') as $cert) {
    $inv['acme'][] = ['name' => $cert['name'] ?? '', 'status' => $cert['status'] ?? '',
                      'domains' => array_map(fn($d) => $d['name'] ?? '', $cert['a_domainlist']['item'] ?? [])];
}
$inv['vpn'] = ['wireguard_tunnels' => count($get('installedpackages/wireguard/tunnels/item')),
               'wireguard_peers' => count($get('installedpackages/wireguard/peers/item')),
               'openvpn_servers' => count($get('openvpn/openvpn-server')), 'ipsec_phase1' => count($get('ipsec/phase1')),
               'tailscale' => $get('installedpackages/tailscale', null) !== null];
$inv['services'] = [
    'packages' => array_map(fn($p) => $p['name'] ?? '', $get('installedpackages/package')),
    'dyndns' => array_map(fn($d) => ($d['type'] ?? '') . '@' . ($d['interface'] ?? ''), $get('dyndnses/dyndns')),
    'syslog_remote' => $get('syslog/remoteserver', ''),
    'ntp_interfaces' => $get('ntpd/interface', 'all'),
    // Cron: the program only, arguments may carry tokens.
    'cron' => array_map(fn($c) => strtok((string)($c['command'] ?? ''), ' '), $get('cron/item')),
];
sort($inv['services']['packages']);
sort($inv['services']['cron']);
ksort($inv['aliases']);
ksort($inv['filter']);
print(json_encode($inv, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . "\n");
