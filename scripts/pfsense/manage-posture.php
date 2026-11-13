<?php

require_once('/etc/inc/config.inc');
require_once('/etc/inc/service-utils.inc');

if (!defined('NABLA_POSTURE_ACTION')) {
    fwrite(STDERR, "ERROR: invoke this helper through diagnose-recover.sh\n");
    exit(2);
}

$apply = (string)NABLA_POSTURE_ACTION === 'apply';

// Netgate 1100 posture from the 2026-11-13 incident; pfREST 2.11 exposes no Snort,
// CrowdSec or Service Watchdog endpoint, so this runs locally through SSH.
const NABLA_SNORT_OFF_FLAGS = ['emergingthreats', 'openappid_detectors', 'openappid_rules_detectors'];
const NABLA_SNORT_IFACE = 'wan';
const NABLA_SNORT_MEMCAP = '33554432';
const NABLA_SNORT_ALIAS = 'snort_http_inspect';
const NABLA_SNORT_ALIAS_PORTS = '80';
const NABLA_CROWDSEC_LAPI_URL = 'http://172.17.0.24:8084/';
const NABLA_CROWDSEC_SUPERVISOR_PID = '/var/run/crowdsec_daemon.pid';

$changed = ['snort_rules' => false, 'snort_iface' => false, 'watchdog' => false, 'crowdsec' => false];
$drift = 0;

function nabla_report(string $name, string $current, string $expected): bool {
    global $drift;
    if ($current === $expected) {
        printf("OK: posture_%s=%s\n", $name, $current);
        return false;
    }
    $drift++;
    printf("WARN: posture_%s=%s expected=%s\n", $name, $current === '' ? '<empty>' : $current, $expected);
    return true;
}

if ($apply) {
    // A package install writes back the config it loaded at start (2026-11-13 22:53).
    exec("pgrep -f 'pkg add|pkg-static (install|upgrade)|rc.packages|pfSense-upgrade'", $busy);
    if ($busy) {
        fwrite(STDERR, "ERROR: a package install or upgrade is running; retry when it ends\n");
        exit(3);
    }
}

// Snort: no ET Open/OpenAppID downloads, so the nightly rebuild stays small.
foreach (NABLA_SNORT_OFF_FLAGS as $flag) {
    $path = "installedpackages/snortglobal/{$flag}";
    if (nabla_report("snort_{$flag}", config_get_path($path, '') === 'on' ? 'on' : 'off', 'off') && $apply) {
        config_set_path($path, 'off');
        $changed['snort_rules'] = true;
    }
}

$alias_idx = null;
foreach (config_get_path('aliases/alias', []) as $idx => $alias) {
    if (($alias['name'] ?? '') === NABLA_SNORT_ALIAS) {
        $alias_idx = $idx;
    }
}
$alias_ports = $alias_idx === null ? '' : (string)config_get_path("aliases/alias/{$alias_idx}/address", '');
if (nabla_report('alias_' . NABLA_SNORT_ALIAS, $alias_ports, NABLA_SNORT_ALIAS_PORTS) && $apply) {
    $alias = [
        'name' => NABLA_SNORT_ALIAS,
        'type' => 'port',
        'address' => NABLA_SNORT_ALIAS_PORTS,
        'descr' => 'Snort HTTP Inspect ports (Netgate 1100 memory budget)',
        'detail' => 'HTTP',
    ];
    // Only Snort reads this alias, so no filter reload is needed.
    config_set_path($alias_idx === null ? 'aliases/alias/' : "aliases/alias/{$alias_idx}", $alias);
    $changed['snort_iface'] = true;
}

$rules = config_get_path('installedpackages/snortglobal/rule', []);
$iface_idx = null;
foreach ($rules as $idx => $rule) {
    if (($rule['interface'] ?? '') === NABLA_SNORT_IFACE) {
        $iface_idx = $idx;
    }
}
if ($iface_idx === null) {
    printf("WARN: posture_snort_%s=missing expected=configured\n", NABLA_SNORT_IFACE);
    $drift++;
} else {
    $base = "installedpackages/snortglobal/rule/{$iface_idx}";
    if (nabla_report('snort_http_memcap', (string)config_get_path("{$base}/http_inspect_memcap", ''), NABLA_SNORT_MEMCAP) && $apply) {
        config_set_path("{$base}/http_inspect_memcap", NABLA_SNORT_MEMCAP);
        $changed['snort_iface'] = true;
    }
    foreach (config_get_path("{$base}/http_inspect_engine/item", []) as $eidx => $engine) {
        if (($engine['name'] ?? '') !== 'default') {
            continue;
        }
        if (nabla_report('snort_http_ports', (string)($engine['ports'] ?? ''), NABLA_SNORT_ALIAS) && $apply) {
            config_set_path("{$base}/http_inspect_engine/item/{$eidx}/ports", NABLA_SNORT_ALIAS);
            $changed['snort_iface'] = true;
        }
    }
}

// Service Watchdog: restart Unbound after an OOM, never the CrowdSec engine of Small mode.
$watched = array_column(config_get_path('installedpackages/servicewatchdog/item', []), 'name');
if (nabla_report('watchdog_unbound', in_array('unbound', $watched, true) ? 'watched' : 'absent', 'watched') && $apply) {
    foreach (get_services() as $service) {
        if (($service['name'] ?? '') === 'unbound') {
            config_set_path('installedpackages/servicewatchdog/item/', $service);
            $changed['watchdog'] = true;
        }
    }
}
if (nabla_report('watchdog_crowdsec', in_array('crowdsec', $watched, true) ? 'watched' : 'absent', 'absent') && $apply) {
    $items = array_values(array_filter(
        config_get_path('installedpackages/servicewatchdog/item', []),
        static fn(array $item): bool => ($item['name'] ?? '') !== 'crowdsec'
    ));
    config_set_path('installedpackages/servicewatchdog/item', $items);
    $changed['watchdog'] = true;
}

// CrowdSec Small: firewall bouncer only, decisions from the TrueNAS LAPI.
$cs = 'installedpackages/crowdsec/config/0';
$cs_expected = ['enable_agent' => '', 'enable_lapi' => '', 'enable_fw_bouncer' => 'on', 'remote_lapi_url' => NABLA_CROWDSEC_LAPI_URL];
if (!is_array(config_get_path($cs))) {
    // Without the package page saved once, a partial section would break its resync.
    nabla_report('crowdsec_package', 'unconfigured', 'configured');
    $cs_expected = [];
}
foreach ($cs_expected as $field => $value) {
    if (nabla_report("crowdsec_{$field}", (string)config_get_path("{$cs}/{$field}", ''), $value) && $apply) {
        config_set_path("{$cs}/{$field}", $value);
        $changed['crowdsec'] = true;
    }
}
// The key comes from the TrueNAS LAPI and is entered in the GUI; never written or printed here.
nabla_report('crowdsec_bouncer_key', config_get_path("{$cs}/remote_fw_bouncer_api_key", '') === '' ? 'empty' : 'set', 'set');
$supervisor = trim((string)@file_get_contents(NABLA_CROWDSEC_SUPERVISOR_PID));
$supervisor_alive = ctype_digit($supervisor) && posix_kill((int)$supervisor, 0);
nabla_report('crowdsec_engine_supervisor', $supervisor_alive ? 'running' : 'absent', 'absent');

if (!$apply) {
    printf("posture_summary drift=%d mode=check\n", $drift);
    exit(0);
}

if (in_array(true, $changed, true)) {
    if ($changed['snort_rules']) {
        require_once('/usr/local/pkg/snort/snort.inc');
        // Same pruning as Snort Global Settings: drop categories of disabled downloads.
        foreach (config_get_path('installedpackages/snortglobal/rule', []) as $idx => $rule) {
            $sets = array_filter(
                explode('||', (string)($rule['rulesets'] ?? '')),
                static fn(string $set): bool =>
                    strpos($set, ET_OPEN_FILE_PREFIX) === false && strpos($set, OPENAPPID_FILE_PREFIX) === false
            );
            config_set_path("installedpackages/snortglobal/rule/{$idx}/rulesets", implode('||', $sets));
        }
    }
    write_config('nabla: apply pfSense posture (diagnose-recover.sh --apply-posture)');
    echo "INFO: posture config written\n";
}

if ($changed['snort_rules'] || $changed['snort_iface']) {
    require_once('/usr/local/pkg/snort/snort.inc');
    sync_snort_package_config();
    $rule = config_get_path("installedpackages/snortglobal/rule/{$iface_idx}", []);
    $if_real = get_real_interface($rule['interface'] ?? NABLA_SNORT_IFACE);
    if ($rule && snort_is_running($rule['uuid'])) {
        snort_stop($rule, $if_real);
        snort_start($rule, $if_real, true);
        echo "INFO: snort restarted on " . NABLA_SNORT_IFACE . "\n";
    }
}

if ($changed['watchdog']) {
    require_once('/usr/local/pkg/servicewatchdog.inc');
    servicewatchdog_cron_job();
    echo "INFO: service watchdog cron refreshed\n";
}

// The daemon(8) supervisor restarts a crowdsec that exits fatally when agent and LAPI are
// off, and that loop also blocks the rc.d stop of the package resync.
if ($supervisor_alive) {
    posix_kill((int)$supervisor, SIGTERM);
    echo "INFO: crowdsec engine supervisor stopped\n";
}
if ($changed['crowdsec']) {
    require_once('/usr/local/pkg/crowdsec.inc');
    crowdsec_resync_config();
    echo "INFO: crowdsec configuration resynced\n";
}

printf("posture_summary drift=%d mode=apply\n", $drift);
