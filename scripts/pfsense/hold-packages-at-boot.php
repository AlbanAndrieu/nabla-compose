<?php
// Keep pfBlockerNG and the CrowdSec firewall bouncer off at boot and on WAN up: on 17/11 the eMMC
// write burst that suspended the ZFS pool came with their restart (php_pfb, crowdsec rc scripts).
// Operator decision (17/11): they start by hand once the box is stable. Incident:
// docs/pfsense/incidents/2026-11-17-pfsense-userland-freeze.md
// rc.start_packages and "service reload packages" run sync_package() then start_service() for every
// installed package, so the package's own enable flag is what keeps them down.
// While held, the pfBlockerNG block rules and CrowdSec decisions are NOT enforced (sshguard and the
// WAN GUI guard stay). "start" re-enables both and persists until "apply" runs again.
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/hold-packages-at-boot.php
require_once('config.inc');
require_once('pkg-utils.inc');
require_once('service-utils.inc');

const FLAGS = [
    'pfBlockerNG' => 'installedpackages/pfblockerng/config/0/enable_cb',
    'crowdsec' => 'installedpackages/crowdsec/config/0/enable_fw_bouncer',
];
const SERVICES = ['pfb_filter', 'pfb_dnsbl', 'crowdsec_firewall', 'crowdsec'];

$mode = $argv[1] ?? 'check';
if (!in_array($mode, ['check', 'apply', 'start'], true)) {
    print("ERROR: mode must be check, apply or start\n");
    exit(2);
}
$want_on = $mode === 'start';
$changes = 0;
foreach (FLAGS as $package => $path) {
    $value = config_get_path($path);
    if ($value === null) {
        print("INFO: {$package} not configured ({$path} absent)\n");
        continue;
    }
    $on = $value === 'on';
    if ($on === $want_on) {
        printf("OK: %s %s at boot\n", $package, $on ? 'starts' : 'is held');
    } else {
        printf("CHANGE: %s %s at boot\n", $package, $on ? 'starts' : 'is held');
        $changes++;
    }
}
foreach (SERVICES as $service) {
    if (is_service_running($service)) {
        printf("%s: service %s is running\n", $want_on ? 'INFO' : 'WARN', $service);
        $changes += $want_on ? 0 : 1;
    }
}
printf("summary: %d change(s), mode=%s\n", $changes, $mode);
if ($mode === 'check' || $changes === 0) {
    exit(0);
}
foreach (FLAGS as $package => $path) {
    if (config_get_path($path) !== null) {
        config_set_path($path, $want_on ? 'on' : '');
    }
}
write_config($want_on ? 'nabla: start pfBlockerNG and CrowdSec bouncer by hand'
    : 'nabla: hold pfBlockerNG and CrowdSec bouncer at boot (eMMC write bursts, incident 2026-11-17)');
// The package resync starts or stops what its settings call for (DNSBL stays off in IP-only mode).
foreach (array_keys(FLAGS) as $package) {
    sync_package($package);
}
foreach ($want_on ? [] : SERVICES as $service) {
    if (is_service_running($service)) {
        stop_service($service);
    }
}
print($want_on ? "OK: pfBlockerNG and CrowdSec bouncer enabled and started\n"
    : "OK: pfBlockerNG and CrowdSec bouncer held, services stopped\n");
