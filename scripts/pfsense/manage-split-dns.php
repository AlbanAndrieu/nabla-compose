<?php
// pfSense local-only configuration reconciliation; invoked over approved SSH.
// This script deliberately never prints full config.xml or secret material.
require_once('/etc/inc/config.inc');
$action = getenv('NABLA_SPLIT_DNS_ACTION') ?: 'check';
if (!in_array($action, ['check', 'apply'], true)) {
    fwrite(STDERR, "ERROR: invalid NABLA_SPLIT_DNS_ACTION\n");
    exit(2);
}

const NABLA_PRIVATE_ZONE = 'int.albandrieu.com';
const NABLA_PIHOLE_DNS = '172.17.0.24';

$overrides = config_get_path('unbound/domainoverrides', []);
if (!is_array($overrides)) {
    fwrite(STDERR, "ERROR: unexpected domainoverrides structure\n");
    exit(3);
}
if (isset($overrides['domain'])) {
    fwrite(STDERR, "ERROR: unexpected single override object; inspect manually\n");
    exit(3);
}
$matching = [];
foreach ($overrides as $key => $entry) {
    if (!is_array($entry)) {
        fwrite(STDERR, "ERROR: malformed domain override; refusing to modify\n");
        exit(3);
    }
    if (strcasecmp(rtrim((string)($entry['domain'] ?? ''), '.'), NABLA_PRIVATE_ZONE) === 0) {
        $matching[$key] = $entry;
    }
}
if (count($matching) > 1) {
    fwrite(STDERR, "ERROR: duplicate private domain overrides; resolve manually\n");
    exit(3);
}
$entry = count($matching) === 1 ? reset($matching) : null;
$matchesExpected = $entry !== null
    && (string)($entry['ip'] ?? '') === NABLA_PIHOLE_DNS
    && !isset($entry['forward_tls_upstream'])
    && empty($entry['tls_hostname']);
$out = strtolower(trim((string)config_get_path('unbound/outgoing_interface', 'all')));
$out = $out === '' ? 'all' : $out;
$enabled = config_path_enabled('unbound');
$forwarding = config_path_enabled('unbound', 'forwarding');

if ($entry === null) {
    echo "DRIFT: split_dns_override=MISSING expected=" . NABLA_PRIVATE_ZONE . "->" . NABLA_PIHOLE_DNS . "\n";
} elseif ($matchesExpected) {
    echo "PASS: split_dns_override=" . NABLA_PRIVATE_ZONE . "->" . NABLA_PIHOLE_DNS . "\n";
} else {
    echo "DRIFT: split_dns_override=CONFLICT expected=" . NABLA_PRIVATE_ZONE . "->" . NABLA_PIHOLE_DNS . " (will not overwrite)\n";
}
if ($out !== 'all') {
    echo "DRIFT: unbound_outgoing_interfaces=" . $out . " expected=all\n";
} else {
    echo "PASS: unbound_outgoing_interfaces=all\n";
}
echo ($enabled ? "PASS" : "DRIFT") . ": unbound_enabled=" . ($enabled ? "yes" : "no") . "\n";
echo ($forwarding ? "DRIFT" : "PASS") . ": unbound_global_forwarding=" . ($forwarding ? "enabled" : "disabled") . "\n";

if ($action === 'check') {
    echo "result=CHECK_ONLY_NO_MUTATION\n";
    exit(0);
}
// Never mutate unexpected configurations, or during concurrent package installs.
if (function_exists('posix_geteuid') && posix_geteuid() !== 0) {
    fwrite(STDERR, "ERROR: root privilege required for --apply\n");
    exit(77);
}
if (!$enabled) {
    fwrite(STDERR, "ERROR: resolver disabled; refusing to enable automatically\n");
    exit(3);
}
if ($entry !== null && !$matchesExpected) {
    fwrite(STDERR, "ERROR: conflicting private override; no changes performed\n");
    exit(3);
}
if ($out !== 'wan' && $out !== 'all') {
    fwrite(STDERR, "ERROR: custom Unbound outgoing interface selection; no changes performed\n");
    exit(3);
}
if ($forwarding) {
    fwrite(STDERR, "ERROR: general forwarding enabled; requires manual architectural review\n");
    exit(3);
}
exec("pgrep -f 'pkg add|pkg-static (install|upgrade)|rc.packages|pfSense-upgrade'", $busy);
if (!empty($busy)) {
    fwrite(STDERR, "ERROR: package installation/upgrade running; refusing concurrent change\n");
    exit(3);
}
$changed = false;
if ($entry === null) {
    $overrides[] = [
        'domain' => NABLA_PRIVATE_ZONE,
        'ip' => NABLA_PIHOLE_DNS,
        'descr' => 'nabla-compose: internal split DNS via Pi-hole',
        'tls_hostname' => '',
    ];
    config_set_path('unbound/domainoverrides', $overrides);
    $changed = true;
}
if ($out !== 'all') {
    config_set_path('unbound/outgoing_interface', 'all');
    $changed = true;
}
if ($changed) {
    write_config('nabla-compose: restore private Unbound Domain Override and outgoing interfaces');
    mark_subsystem_dirty('unbound');
    echo "result=APPLY_CHANGED_RESTART_REQUIRED\n";
} else {
    echo "result=ALREADY_CONVERGED_NO_RESTART\n";
}
