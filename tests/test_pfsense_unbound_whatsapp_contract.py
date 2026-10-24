"""Offline contract for bounded pfSense DNS incident diagnostics."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh"


class UnboundWifiContract(unittest.TestCase):
    def test_script_parses_and_help_needs_no_ssh(self):
        self.assertEqual(subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, check=False
        ).returncode, 0)
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True,
            text=True, check=False
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)

    def test_usage_errors_use_stderr(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--invalid"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--check", result.stderr)

    def test_awk_crowdsec_patterns_are_portable(self):
        # Test the exact awk block from the remote read-only script.
        shell = SCRIPT.read_text(encoding="utf-8")
        block = shell.split(
            "echo '=== CrowdSec engine vs firewall bouncer (separate processes) ==='",
            1,
        )[1].split("echo '=== Recent CrowdSec pressure signatures", 1)[0]
        match = re.search(r"awk '(.*?)'", block, re.DOTALL)
        self.assertIsNotNone(match)
        sample = (
            "12 81000 4.0 /usr/local/bin/crowdsec -c /tmp/config.yaml\n"
            "13 9000 0.2 /usr/local/bin/crowdsec-firewall-bouncer -c /tmp/bouncer.yaml\n"
        )
        result = subprocess.run(
            ["awk", match.group(1)], input=sample, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("crowdsec_engine_pid=12", result.stdout)
        self.assertIn("crowdsec_bouncer_pid=13", result.stdout)

    def test_awk_and_feed_lines_use_real_newline_escapes(self):
        shell = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(r'task=%s\n",', shell)
        self.assertNotIn(r'task=%s\\n",', shell)
        self.assertIn(r"printf '%s %s\n'", shell)
        self.assertNotIn(r"printf '%s %s\\n'", shell)

    def test_requires_explicit_read_only_mode(self):
        for args in ([], ["--apply"], ["--check", "--apply"]):
            result = subprocess.run(
                ["bash", str(SCRIPT), *args], capture_output=True,
                text=True, check=False
            )
            self.assertEqual(result.returncode, 2)

    def test_rejects_bad_ssh_target_before_network(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--check", "--target", "host;danger"],
            capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)

    def test_snort_cron_classifies_update_and_housekeeping_separately(self):
        script = SCRIPT.read_text(encoding="utf-8")
        cron = script.split(
            "echo '=== Jobs scheduled near repeated 02:10 OOM (schedule + type only) ==='",
            1,
        )[1].split("echo '=== Snort updater evidence:", 1)[0]
        match = re.search(r"awk '(.*?)' /etc/crontab", cron, re.DOTALL)
        self.assertIsNotNone(match)
        sample = (
            "9 2,14 * * * root /usr/local/bin/php -f "
            "/usr/local/pkg/snort/snort_check_for_rule_updates.inc\n"
            "*/5 * * * * root /usr/bin/nice -n20 "
            "/usr/local/pkg/snort/snort_check_cron_misc.inc\n"
        )
        result = subprocess.run(
            ["awk", match.group(1)], input=sample, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cron_minute=9 cron_hour=2,14", result.stdout)
        self.assertIn("task=snort_rules_update", result.stdout)
        self.assertIn("task=snort_housekeeping", result.stdout)
        self.assertNotIn("/usr/local/pkg/snort/", result.stdout)

    def test_snort_logs_expose_metadata_not_rule_downloads(self):
        script = SCRIPT.read_text(encoding="utf-8")
        evidence = script.split(
            "echo '=== Snort updater evidence:", 1
        )[1].split(
            "echo '=== CrowdSec engine vs firewall bouncer", 1
        )[0]
        self.assertIn("stat -f", evidence)
        self.assertIn("modified=%Sm size_bytes=%z", evidence)
        self.assertNotIn("cat \"$f\"", evidence)
        self.assertNotIn("grep -i snort", evidence)

    def test_php_fpm_memory_footprint_is_aggregate_and_non_secret(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split(
            "echo '=== PHP-FPM worker footprint", 1
        )[1].split(
            "echo '=== RAM-backed /tmp and /var capacity", 1
        )[0]
        match = re.search(r"awk '(.*?)'", section, re.DOTALL)
        self.assertIsNotNone(match)
        sample = (
            "43576 php-fpm: pool nginx (php-fpm)\n"
            "41300 php-fpm: pool nginx (php-fpm)\n"
            "77000 /usr/local/bin/crowdsec -c /private/config\n"
        )
        result = subprocess.run(
            ["awk", match.group(1)],
            input=sample, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("php_fpm_workers=2", result.stdout)
        self.assertIn("php_fpm_rss_sum_kb=84876", result.stdout)
        self.assertIn("php_fpm_max_worker_rss_kb=43576", result.stdout)
        self.assertNotIn("private", result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertIn("df -k /tmp /var", script)
        self.assertNotIn("sysctl kern.ipc.maxsockbuf=", script)

    def test_scheduled_oom_correlations_are_redacted(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("cron_minute=", script)
        self.assertIn("crowdsec_engine_pid=", script)
        self.assertIn("crowdsec_bouncer_pid=", script)
        self.assertIn("crowdsec_stuck_lines=", script)
        runbook = (
            ROOT / "docs/runbooks/2026-10-24-pfsense-unbound-pfblocker-whatsapp.md"
        )
        self.assertTrue(runbook.is_file())
        self.assertIn("02:10", runbook.read_text(encoding="utf-8"))
        self.assertNotIn("cat /conf/config.xml", script)
        self.assertNotIn("service crowdsec restart", script)

    def test_uses_strict_batch_ssh_with_no_mutation(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("BatchMode=yes", text)
        self.assertIn("unbound-control -c /var/unbound/unbound.conf stats_noreset", text)
        self.assertIn("pfblockerng.php", text)
        self.assertIn("asn_reporting", text)
        self.assertIn("web.whatsapp.com", text)
        for command in (
            "pfctl -F", "service unbound restart", "pfblockerng.php update",
            "configctl unbound restart", "unbound-control flush_zone",
            "rm -rf", "midclt call app.redeploy",
        ):
            self.assertNotIn(command, text)

    def test_never_runs_remote_ssh_if_mode_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "ssh"
            marker = Path(directory) / "called"
            binary.write_text(
                "#!/bin/sh\nprintf called > \"$MARKER\"\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            env = os.environ | {
                "PATH": directory + os.pathsep + os.environ["PATH"],
                "MARKER": str(marker),
            }
            result = subprocess.run(
                ["bash", str(SCRIPT), "--apply"],
                env=env, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(marker.exists())

    def test_process_and_pfblocker_logs_redact_sensitive_arguments(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ps axo pid,rss,pcpu,comm", script)
        self.assertNotIn("ps axo pid,rss,pcpu,command | sort -nr -k2", script)
        section = script.split(
            "echo '=== pfBlockerNG process overlap", 1
        )[1].split("echo '=== Resolver failures", 1)[0]
        blocks = re.findall(r"awk '(.*?)'", section, re.DOTALL)
        self.assertEqual(len(blocks), 2)

        processes = (
            "21 65000 3.5 /usr/local/bin/php -f "
            "/usr/local/pkg/pfblockerng.php --token secret_value\n"
            "22 33000 2.0 /usr/local/sbin/php_pfb --password private_value\n"
            "23 50000 1.0 /usr/bin/awk pfblockerng.php\n"
        )
        result = subprocess.run(
            ["awk", blocks[0]], input=processes, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("process_class=pfblockerng pid=21", result.stdout)
        self.assertIn("process_class=php_pfb pid=22", result.stdout)
        self.assertNotIn("pid=23", result.stdout)
        self.assertNotIn("secret_value", result.stdout)
        self.assertNotIn("private_value", result.stdout)

        logs = (
            "10/24/2026 22:00:09: Downloading IPinfo token=super_secret\n"
            "10/24/2026 22:03:11: DNSBL update PASSED private.domain\n"
        )
        result = subprocess.run(
            ["awk", blocks[1]], input=logs, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pfblocker_event=ipinfo_attempt line=1", result.stdout)
        self.assertIn("pfblocker_event=dnsbl_passed line=2", result.stdout)
        self.assertNotIn("super_secret", result.stdout)
        self.assertNotIn("private.domain", result.stdout)

    def test_crowdsec_rc_probe_is_read_only(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split(
            "echo '=== CrowdSec rc startup flags", 1
        )[1].split("echo '=== Recent CrowdSec pressure signatures", 1)[0]
        self.assertIn('sysrc -n "$key"', section)
        self.assertIn("crowdsec_firewall_bouncer_enable", section)
        self.assertIn("status=%s", section)
        self.assertNotIn("sysrc crowdsec_enable=", section)

    def test_oom_window_expurgates_cron_and_oom_log_contents(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("=== Snort/pfBlockerNG/kernel OOM chronology", script)
        section = script.split(
            "echo '=== Snort/pfBlockerNG/kernel OOM chronology", 1
        )[1].split("echo '=== CrowdSec engine vs firewall bouncer", 1)[0]
        match = re.search(r"awk -v source=\"\$source\" '(.*?)'", section, re.DOTALL)
        self.assertIsNotNone(match)
        fixture = (
            "Oct 24 02:09:00 fw CRON snort_check_for_rule_updates token=sensitive\n"
            "Oct 24 02:10:50 kernel: unbound killed: failed to reclaim memory private.local\n"
        )
        for source, expected in (("cron", "snort_cron"), ("system", "kernel_oom")):
            with self.subTest(source=source):
                result = subprocess.run(
                    ["awk", "-v", f"source={source}", match.group(1)],
                    input=fixture, text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"event={expected}", result.stdout)
                self.assertNotIn("sensitive", result.stdout)
                self.assertNotIn("private.local", result.stdout)
        self.assertIn("tail -n 5000", section)
        for forbidden in ("service snort restart", "service crowdsec stop", "configctl unbound restart"):
            self.assertNotIn(forbidden, section)

    def test_freebsd_syslog_rfc5424_oom_timestamp_and_redaction(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split(
            "echo '=== Snort/pfBlockerNG/kernel OOM chronology", 1
        )[1].split("echo '=== CrowdSec engine vs firewall bouncer", 1)[0]
        match = re.search(r'awk -v source="\$source" \'(.*?)\'', section, re.DOTALL)
        self.assertIsNotNone(match)
        entries = (
            "<3>1 2026-10-24T02:10:50.474019+02:00 pfsense kernel - - - "
            "unbound was killed: failed to reclaim memory password=SECRET\n"
            "<29>1 2026-10-22T22:03:33.361041+02:00 pfsense kernel - - - "
            "unbound killed: failed to reclaim memory token=PRIVATE\n"
            "message containing 2026-10-24T01:02:03+02:00 and "
            "failed to reclaim memory\n"
        )
        result = subprocess.run(
            ["awk", "-v", "source=system", match.group(1)],
            input=entries, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("timestamp=2026-10-24T02:10:50.474019+02:00", result.stdout)
        self.assertIn("timestamp=2026-10-22T22:03:33.361041+02:00", result.stdout)
        self.assertIn("timestamp=unknown", result.stdout)
        self.assertEqual(result.stdout.count("event=kernel_oom"), 3)
        self.assertNotIn("SECRET", result.stdout)
        self.assertNotIn("PRIVATE", result.stdout)

    def test_freebsd_ps_rss_columns_are_sanitized_and_numeric(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("ps axo pid=,rss=,pcpu=,comm=", script)
        section = script.split("printf 'pid rss_kb cpu_pct executable", 1)[1]
        section = section.split("dmesg -a", 1)[0]
        self.assertIn("ps axo pid,rss,pcpu,comm", section)
        awk = re.search(r"awk '(.*?)'", section, re.DOTALL)
        self.assertIsNotNone(awk)
        sample = (
            "PID RSS %CPU COMMAND\n"
            "21619 133112 6.1 unbound\n"
            "56397 85108 11.4 crowdsec\n"
            "junk invalid --password=SECRET php\n"
            "87266 8824 0.0 crowdsec-bouncer\n"
        )
        result = subprocess.run(
            ["awk", awk.group(1)], input=sample,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("21619 133112 6.1 unbound", result.stdout)
        self.assertIn("56397 85108 11.4 crowdsec", result.stdout)
        self.assertNotIn("PID RSS", result.stdout)
        self.assertNotIn("SECRET", result.stdout)

    def test_pfblockerng_events_keep_only_recognized_timestamp_prefix(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split(
            "echo '=== pfBlockerNG process overlap", 1
        )[1].split("echo '=== Resolver failures", 1)[0]
        blocks = re.findall(r"awk '(.*?)'", section, re.DOTALL)
        self.assertEqual(len(blocks), 2)
        fixture = (
            "10/25/2026 00:04:54: Restarting DNSBL Service token=PRIVATE\n"
            "2026-10-24T22:03:11 DNSBL update PASSED private.example\n"
            "no timestamp UPDATE PROCESS ENDED password=SECRET\n"
        )
        result = subprocess.run(
            ["awk", blocks[1]], input=fixture, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "pfblocker_event=dnsbl_restart line=1 timestamp=10/25/2026 00:04:54",
            result.stdout,
        )
        self.assertIn(
            "pfblocker_event=dnsbl_passed line=2 timestamp=2026-10-24T22:03:11",
            result.stdout,
        )
        self.assertIn("pfblocker_event=update_ended line=3 timestamp=unknown", result.stdout)
        self.assertNotIn("PRIVATE", result.stdout)
        self.assertNotIn("private.example", result.stdout)
        self.assertNotIn("SECRET", result.stdout)


if __name__ == "__main__":
    unittest.main()
