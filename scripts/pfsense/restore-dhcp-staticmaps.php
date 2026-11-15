<?php
// Add the October DHCP static mappings (Talos .50-.52 and others) missing after a boot-environment
// fallback. Match by MAC, never overwrite; print IP and hostname only, no MAC. Check first, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/restore-dhcp-staticmaps.php
// Runbook: docs/runbooks/pfsense-26.07-upgrade.md
require_once('config.inc');
require_once('functions.inc');
require_once('services.inc');
require_once('xmlparse.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const NABLA_SRC_BE = 'pfSense/ROOT/default_20260824183037/cf';

$mp = '/tmp/becf.' . getmypid();
mkdir($mp);
exec('mount -t zfs -o ro ' . NABLA_SRC_BE . ' ' . escapeshellarg($mp), $out, $rc);
if ($rc !== 0) {
    rmdir($mp);
    fwrite(STDERR, "ERROR: cannot mount the October cf dataset\n");
    exit(1);
}
$oct = parse_xml_config("{$mp}/conf/config.xml", 'pfsense');
exec('umount ' . escapeshellarg($mp));
rmdir($mp);

$added = 0;
foreach ($oct['dhcpd'] ?? [] as $if => $scope) {
    $cur = config_get_path("dhcpd/{$if}/staticmap", []);
    if (config_get_path("dhcpd/{$if}") === null) {
        printf("SKIP: interface %s has no DHCP scope on default_clone\n", $if);
        continue;
    }
    $macs = array_map('strtolower', array_column($cur, 'mac'));
    $ips = array_column($cur, 'ipaddr');
    foreach ($scope['staticmap'] ?? [] as $map) {
        $mac = strtolower($map['mac'] ?? '');
        $ip = $map['ipaddr'] ?? '';
        $label = sprintf("%s %s (%s)", $if, $ip, $map['hostname'] ?? ($map['descr'] ?? '?'));
        if ($mac === '' || in_array($mac, $macs, true)) {
            continue;
        }
        if ($ip !== '' && in_array($ip, $ips, true)) {
            echo "CONFLICT: {$label} IP already mapped to another MAC, skipped\n";
            continue;
        }
        echo "ADD: {$label}\n";
        $cur[] = $map;
        $added++;
    }
    if ($apply) {
        config_set_path("dhcpd/{$if}/staticmap", $cur);
    }
}
if ($added === 0) {
    echo "OK: no missing static mapping\n";
    exit(0);
}
if (!$apply) {
    echo "CHANGE: {$added} static mapping(s) to add\n";
    exit(0);
}
write_config("Restore {$added} DHCP static mappings from the October boot environment");
services_dhcpd_configure();
echo "OK: {$added} static mapping(s) added, DHCP reconfigured\n";
