<?php
// Switch pfSense's WAN between the static public address (Freebox in bridge mode) and DHCP (Freebox in
// router mode, pfSense on a pinned lease with the DMZ). In bridge mode the Freebox also hands the public
// address out over DHCP, so "dhcp" runs first and the Freebox switch second: Internet keeps working.
// Procedure: docs/pfsense/runbooks/freebox-router-mode.md
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/wan-addressing.php
//   modes: check | dhcp | static <ipv4>/<prefix> | renew
// dhcp disables the static gateway WANGW (kept for the way back) and moves rules pinned to it onto
// WAN_DHCP; static does the reverse. IPv6 (dhcp6 + track6) is left as is.
require_once('config.inc');
require_once('functions.inc');
require_once('interfaces.inc');
require_once('filter.inc');
require_once('system.inc');

const GW_STATIC = 'WANGW';
const GW_DHCP = 'WAN_DHCP';

$mode = $argv[1] ?? 'check';
if (!in_array($mode, ['check', 'dhcp', 'static', 'renew'], true)) {
    print("ERROR: mode must be check, dhcp, static <ipv4>/<prefix> or renew\n");
    exit(2);
}
$target = null;
if ($mode === 'static') {
    [$ip, $prefix] = array_pad(explode('/', $argv[2] ?? '', 2), 2, '');
    if (!filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) || !ctype_digit($prefix) || $prefix < 1 || $prefix > 32) {
        print("ERROR: static needs <ipv4>/<prefix>, e.g. static 203.0.113.10/24\n");
        exit(2);
    }
    $target = [$ip, $prefix];
}

function reconfigure_wan(): void {
    interface_configure('wan', true);
    system_routing_configure('wan');
    filter_configure();
}

$wan = config_get_path('interfaces/wan', []);
$gateways = config_get_path('gateways/gateway_item', []);
$rules = config_get_path('filter/rule', []);
$is_dhcp = ($wan['ipaddr'] ?? '') === 'dhcp';
printf("INFO: WAN %s\n", $is_dhcp ? 'uses DHCP' : sprintf('is static %s/%s via %s', $wan['ipaddr'] ?? '?', $wan['subnet'] ?? '?', $wan['gateway'] ?? '?'));

if ($mode === 'renew') {
    if (!$is_dhcp) {
        print("ERROR: renew only applies to a DHCP WAN\n");
        exit(1);
    }
    reconfigure_wan();
    printf("OK: WAN renewed, address %s\n", get_interface_ip('wan') ?: 'none yet (retry in a few seconds)');
    exit(0);
}

$static_gw = null;
foreach ($gateways as $i => $gw) {
    if (($gw['name'] ?? '') === GW_STATIC) {
        $static_gw = $i;
    }
}
$pinned = fn($name) => count(array_filter($rules, fn($r) => ($r['gateway'] ?? '') === $name));

if ($mode === 'check') {
    printf("INFO: rules pinned to %s=%d, to %s=%d\n", GW_STATIC, $pinned(GW_STATIC), GW_DHCP, $pinned(GW_DHCP));
    printf("INFO: gateway %s %s\n", GW_STATIC, $static_gw === null ? 'absent' : (isset($gateways[$static_gw]['disabled']) ? 'disabled' : 'enabled'));
    if (!$is_dhcp) {
        // Literal copies of the public address stop matching once the Freebox NATs in front of pfSense.
        foreach (config_get_path('aliases/alias', []) as $alias) {
            if (in_array($wan['ipaddr'] ?? '', preg_split('/\s+/', trim($alias['address'] ?? '')), true)) {
                printf("WARN: alias %s holds the WAN address literally: review it before dhcp\n", $alias['name'] ?? '?');
            }
        }
    }
    foreach (config_get_path('dyndnses/dyndns', []) as $d) {
        if (($d['interface'] ?? '') === 'wan') {
            printf("INFO: dynamic DNS %s on WAN: behind the Freebox it must read the public IP via a check IP service\n", $d['type'] ?? '?');
        }
    }
    print("summary: check only\n");
    exit(0);
}

if ($static_gw === null) {
    printf("ERROR: gateway %s not found: it carries the public gateway for the way back\n", GW_STATIC);
    exit(1);
}
[$from, $to] = $mode === 'dhcp' ? [GW_STATIC, GW_DHCP] : [GW_DHCP, GW_STATIC];
$changes = [];
if ($mode === 'dhcp' && !$is_dhcp) {
    $changes[] = 'WAN static -> DHCP';
    $wan['ipaddr'] = 'dhcp';
    unset($wan['subnet'], $wan['gateway']);
}
if ($mode === 'static' && ($wan['ipaddr'] ?? '') . '/' . ($wan['subnet'] ?? '') !== implode('/', $target)) {
    $changes[] = sprintf('WAN %s -> static %s/%s via %s', $is_dhcp ? 'DHCP' : 'static', $target[0], $target[1], GW_STATIC);
    [$wan['ipaddr'], $wan['subnet']] = $target;
    $wan['gateway'] = GW_STATIC;
}
$disable = $mode === 'dhcp';
if (isset($gateways[$static_gw]['disabled']) !== $disable) {
    $changes[] = sprintf('gateway %s %s', GW_STATIC, $disable ? 'disabled' : 'enabled');
    if ($disable) {
        $gateways[$static_gw]['disabled'] = '';
    } else {
        unset($gateways[$static_gw]['disabled']);
    }
}
if ($pinned($from) > 0) {
    $changes[] = sprintf('%d rule(s) %s -> %s', $pinned($from), $from, $to);
    foreach ($rules as &$rule) {
        if (($rule['gateway'] ?? '') === $from) {
            $rule['gateway'] = $to;
        }
    }
    unset($rule);
}
foreach ($changes as $change) {
    print("CHANGE: {$change}\n");
}
printf("summary: %d change(s), mode=%s\n", count($changes), $mode);
if (!$changes) {
    print("OK: WAN already in {$mode} mode\n");
    exit(0);
}
config_set_path('interfaces/wan', $wan);
config_set_path('gateways/gateway_item', $gateways);
config_set_path('filter/rule', $rules);
write_config("nabla: WAN {$mode} (Freebox " . ($mode === 'dhcp' ? 'router or bridge' : 'bridge') . ' mode, runbook freebox-router-mode)');
reconfigure_wan();
printf("OK: WAN in %s mode, address %s\n", $mode, get_interface_ip('wan') ?: 'pending');
