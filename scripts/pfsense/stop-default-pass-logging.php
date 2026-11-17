<?php
// Stop logging the packets matched by pfSense's default pass rules ("let out anything from
// firewall host itself", trackers 10000057xx/58xx): 92 % of filterlog on 17/11, 630 to 3400
// lines/min instead of ~30 in October. Every line goes through syslogd, the pfBlockerNG filterlog
// pipe and the 2018 eMMC (no RAM disk). Incident: docs/pfsense/incidents/2026-11-17-pfsense-userland-freeze.md
// The key is inverted: <nologdefaultpass> PRESENT means "log the default pass rules"
// (status_logs_settings.php: logdefaultpass = isset(nologdefaultpass)). October config: absent.
// Run from the workstation, check first:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/stop-default-pass-logging.php
// then "php -- apply", then check again about a minute later (the filter reload is queued).
// Config History keeps the previous config.xml; resync the fallback BE afterwards.
require_once('config.inc');
require_once('filter.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
$logged = config_get_path('syslog/nologdefaultpass') !== null;
print($logged
    ? "CHANGE: syslog/nologdefaultpass is set, so the default pass rules are logged\n"
    : "OK: config.xml does not log the default pass rules\n");

// rules.debug is what pf loaded: auto rules carry ridentifier 100000xxxx, user rules a timestamp.
// Tests point NABLA_RULES_DEBUG at a fixture.
$rules = @file_get_contents(getenv('NABLA_RULES_DEBUG') ?: '/tmp/rules.debug');
$live = $rules === false ? null : preg_match_all('/^pass\b[^\n]*\blog\b[^\n]*\bridentifier 100000\d{4}\b/m', $rules);
if ($live === null) {
    print("INFO: rules.debug unreadable, live ruleset not checked\n");
} elseif ($live === 0) {
    print("OK: rules.debug logs no default pass rule\n");
} elseif ($logged) {
    printf("INFO: rules.debug logs %d default pass rule(s)\n", $live);
} else {
    printf("WARN: rules.debug still logs %d default pass rule(s): filter reload pending or failed\n", $live);
}

$reload_only = !$logged && (int)$live > 0;
printf("summary: %d change(s), mode=%s\n", (int)$logged + (int)$reload_only, $apply ? 'apply' : 'check');
if (!$apply || (!$logged && !$reload_only)) {
    exit(0);
}
if ($logged) {
    $syslog = config_get_path('syslog', []);
    unset($syslog['nologdefaultpass']);
    config_set_path('syslog', $syslog);
    write_config('nabla: stop logging the default pass rules (filterlog flood, incident 2026-11-17)');
}
// filter_configure() only queues the reload; re-run check to see rules.debug converge.
filter_configure();
print($logged ? "OK: config written, filter reload queued\n" : "OK: filter reload queued\n");
