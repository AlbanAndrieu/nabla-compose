<?php
// Remove the CAs that nothing uses and that are either expired (pfSense lists them in its nightly
// "CA/Certificate entries are expiring" notice: 13 ExpressVPN CAs of 2022 on 16/11) or ACME issuers
// ("Acmecert: ..."), which the ACME package re-imports whenever a renewal needs them.
// Run from the workstation, check first:
//   ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/remove-unused-cas.php
// then "php -- apply", then check again. Config History keeps the previous config.xml.
require_once('config.inc');

$apply = ($argv[1] ?? 'check') === 'apply';
$cas = config_get_path('ca', []);
// Any refid found elsewhere in the config (cert caref, OpenVPN, IPsec, CRL, packages) counts as a use.
$rest = config_get_path('', []);
unset($rest['ca']);
$elsewhere = serialize($rest);

$drop = [];
foreach ($cas as $i => $ca) {
    $refid = $ca['refid'] ?? '';
    $x509 = openssl_x509_parse(base64_decode($ca['crt'] ?? ''));
    $acme = str_starts_with($ca['descr'] ?? '', 'Acmecert:');
    if ($refid === '' || !$x509 || ($x509['validTo_time_t'] >= time() && !$acme)) {
        continue;
    }
    $why = $x509['validTo_time_t'] < time() ? 'expired ' . date('Y-m-d', $x509['validTo_time_t']) : 'ACME issuer';
    $children = array_filter($cas, fn($c) => ($c['caref'] ?? '') === $refid);
    // A CA holding its private key is one we issued: never removed by this script.
    if (!empty($ca['prv']) || $children || strpos($elsewhere, $refid) !== false) {
        printf("KEEP: ca %s %s %s but holds a key or is still used\n", $refid, $ca['descr'] ?? '', $why);
        continue;
    }
    printf("CHANGE: ca %s %s %s, unused\n", $refid, $ca['descr'] ?? '', $why);
    $drop[] = $i;
}
printf("summary: %d unused CA(s) to remove out of %d, mode=%s\n", count($drop), count($cas), $apply ? 'apply' : 'check');
if (!$apply || !$drop) {
    exit(0);
}
foreach ($drop as $i) {
    unset($cas[$i]);
}
config_set_path('ca', array_values($cas));
write_config(sprintf('nabla: remove %d unused CA(s)', count($drop)));
echo "OK: config written\n";
