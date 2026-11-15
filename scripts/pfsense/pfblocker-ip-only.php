<?php
// Enable pfBlockerNG IP lists only: DNSBL stays off (Unbound OOM on the 1 GB Netgate 1100,
// incident 2026-11-13) and the discontinued MaxMind_BD_Proxy feed is disabled.
// Run from the workstation, check first, then apply:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/pfblocker-ip-only.php
// Then load the tables from the lists already on disk (no download):
//   ssh -p 9922 admin@172.17.0.1 php /usr/local/www/pfblockerng/pfblockerng.php updateip
// Runbook: docs/runbooks/pfsense-26.07-upgrade.md
require_once('config.inc');
require_once('util.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
require_once('/usr/local/pkg/pfblockerng/pfblockerng.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
const NABLA_GENERAL = 'installedpackages/pfblockerng/config/0';
const NABLA_DNSBL = 'installedpackages/pfblockerngdnsblsettings/config/0/pfb_dnsbl';
const NABLA_LEGACY_FEED = 'MaxMind_BD_Proxy';

if (config_get_path(NABLA_GENERAL) === null) {
    fwrite(STDERR, "ERROR: pfBlockerNG general settings missing; nothing written\n");
    exit(1);
}
$changes = 0;

foreach (['pfblockernglistsv4', 'pfblockernglistsv6'] as $sec) {
    foreach (config_get_path("installedpackages/{$sec}/config", []) as $gi => $grp) {
        foreach ($grp['row'] ?? [] as $ri => $row) {
            if (($row['header'] ?? '') !== NABLA_LEGACY_FEED) {
                continue;
            }
            $st = $row['state'] ?? '';
            printf("%s: %s %s row %s state=%s\n", $st === 'Disabled' ? 'OK' : 'CHANGE', $sec, $grp['aliasname'] ?? '?', NABLA_LEGACY_FEED, $st);
            if ($st !== 'Disabled') {
                $changes++;
                config_set_path("installedpackages/{$sec}/config/{$gi}/row/{$ri}/state", 'Disabled');
            }
        }
    }
}

$dnsbl = config_get_path(NABLA_DNSBL, '');
printf("%s: dnsbl=%s expected=off\n", $dnsbl === 'on' ? 'CHANGE' : 'OK', $dnsbl ?: 'off');
if ($dnsbl === 'on') {
    $changes++;
    config_set_path(NABLA_DNSBL, '');
}

// Top Spammers holds whole countries: with FR, its floating WAN rule blocked our own address
// outbound and cut all IPv4 (2026-11-15 18:43).
$top = 'installedpackages/pfblockerngtopspammers/config/0/countries4';
$countries = array_filter(explode(',', (string)config_get_path($top, '')));
$own = array_intersect($countries, ['FR', 'FR_rep']);
printf("%s: top_spammers_own_country=%s expected=absent\n", $own ? 'CHANGE' : 'OK', $own ? implode('+', $own) : 'absent');
if ($own) {
    $changes++;
    config_set_path($top, implode(',', array_diff($countries, ['FR', 'FR_rep'])));
}

// IPv4 GeoIP only: the v6 lists (190k entries) pushed a filter reload past the 400k pf table-entries
// limit, because old and new tables coexist during a reload (2026-11-15 20:43, Top Spammers never loaded).
// shortcut: assumes WAN has no global IPv6; restore v6 countries with a higher table limit if it gets one.
foreach (config_get_path('installedpackages', []) as $sec => $pkg) {
    $v6 = $pkg['config'][0]['countries6'] ?? '';
    if (!str_starts_with($sec, 'pfblockerng') || $v6 === '') {
        continue;
    }
    $changes++;
    printf("CHANGE: %s countries6=%d expected=0\n", $sec, count(explode(',', $v6)));
    config_set_path("installedpackages/{$sec}/config/0/countries6", '');
}

// A failed reload keeps the previous ruleset silently: every pfB table of the generated rules must be loaded.
preg_match_all('/^table <(pfB_[^>]+)>/m', (string)@file_get_contents('/tmp/rules.debug'), $m);
exec('/sbin/pfctl -sT 2>/dev/null', $loaded);
$missing = array_diff($m[1], array_map('trim', $loaded));
printf("%s: pf_tables_not_loaded=%s\n", $missing ? 'WARN' : 'OK', $missing ? implode(',', $missing) : 'none');

$cb = config_get_path(NABLA_GENERAL . '/enable_cb', '');
printf("%s: enable_cb=%s expected=on\n", $cb === 'on' ? 'OK' : 'CHANGE', $cb ?: 'off');
if ($cb !== 'on') {
    $changes++;
    config_set_path(NABLA_GENERAL . '/enable_cb', 'on');
}

printf("summary: %d change(s), mode=%s\n", $changes, $apply ? 'apply' : 'check');
if (!$apply || $changes === 0) {
    exit(0);
}

write_config('nabla: pfBlockerNG IPv4 lists only (DNSBL off, no v6 GeoIP, MaxMind_BD_Proxy disabled)');
// Same path as a General settings save in the GUI: cron jobs, aliases and rules.
global $pfb;
$pfb['save'] = TRUE;
sync_package_pfblockerng();
print("OK: pfBlockerNG settings saved; run pfblockerng.php updateip to load the tables\n");
