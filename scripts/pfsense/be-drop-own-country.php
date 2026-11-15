<?php
// Drop FR/FR_rep from pfBlockerNG Top Spammers in inactive boot environments (all by default).
// With FR, its floating WAN rule blocked our own address outbound and cut all IPv4 (2026-11-15
// 18:43); a fallback or upgrade boot would do it again. The running BE is fixed by manage-posture.php.
// Targeted text edit: re-serializing another release's config.xml could alter package list tags.
// Run from the workstation, check first, then apply (check-drift.sh runs the check):
//   ssh -p 9922 admin@172.17.0.1 "php -- check [BE...]" < scripts/pfsense/be-drop-own-country.php
const NABLA_OWN = ['FR', 'FR_rep'];
const NABLA_TOP = '#(<pfblockerngtopspammers>.*?<countries4>)(<!\[CDATA\[)?([^<\]]*)(\]\]>)?(</countries4>)#s';

$apply = ($argv[1] ?? 'check') === 'apply';
$only = array_slice($argv, 2);
exec('bectl list -H', $rows);
$changes = 0;
foreach ($rows as $row) {
    [$be, $flags] = preg_split('/\s+/', trim($row));
    if (str_contains($flags, 'N') || ($only && !in_array($be, $only, true))) {
        continue;
    }
    $mp = "/tmp/be-own-country." . getmypid();
    mkdir($mp);
    exec('mount -t zfs -o ' . ($apply ? 'rw' : 'ro') . ' ' . escapeshellarg("pfSense/ROOT/{$be}/cf") . ' ' . escapeshellarg($mp), $out, $rc);
    if ($rc !== 0) {
        rmdir($mp);
        fwrite(STDERR, "ERROR: cannot mount {$be}/cf\n");
        exit(1);
    }
    $file = "{$mp}/conf/config.xml";
    $xml = (string)file_get_contents($file);
    $own = [];
    if (preg_match(NABLA_TOP, $xml, $m)) {
        $own = array_intersect(explode(',', $m[3]), NABLA_OWN);
    }
    if (!$own) {
        echo "OK: {$be} top_spammers_own_country=absent\n";
    } else {
        $changes++;
        printf("CHANGE: %s top_spammers_own_country=%s expected=absent\n", $be, implode('+', $own));
        if ($apply) {
            copy($file, "{$file}.nabla-pre-own-country-" . date('YmdHis'));
            $fixed = preg_replace_callback(NABLA_TOP, static fn($m) => $m[1] . $m[2]
                . implode(',', array_diff(explode(',', $m[3]), NABLA_OWN)) . ($m[4] ?? '') . $m[5], $xml, 1);
            file_put_contents($file, $fixed);
            preg_match(NABLA_TOP, (string)file_get_contents($file), $after);
            $left = array_intersect(explode(',', $after[3] ?? ''), NABLA_OWN);
            echo $left ? "ERROR: {$be} still holds " . implode('+', $left) . "\n" : "OK: {$be} FR/FR_rep dropped; previous copy kept\n";
        }
    }
    exec('umount ' . escapeshellarg($mp));
    rmdir($mp);
}
printf("summary: %d boot environment(s) with an own country in Top Spammers, mode=%s\n", $changes, $apply ? 'apply' : 'check');
