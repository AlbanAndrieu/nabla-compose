"""Offline contracts for read-only pfSense Unbound lifecycle provenance."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/diagnose-unbound-restart-cause.sh"


def extract_remote_shell(source: str) -> str:
    """Extract the SSH heredoc body with or without a trailing renderer pipe.

    Example: ssh host '/bin/sh -s' <<'REMOTE' | pfsense_ui_render
    """
    match = re.search(
        r"(?m)^ssh[^\n]*<<'REMOTE'[^\n]*\n"
        r"(?P<body>.*?)\nREMOTE(?=\n|\Z)",
        source, re.DOTALL,
    )
    if not match:
        raise AssertionError("SSH REMOTE heredoc not found or unterminated")
    return match.group("body")


def remote_awk() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(
        r'tail -n 4000 "\$file" \| awk -v source="\$source" \'(.*?)\''
        r"\s*;\s*then", source, re.DOTALL,
    )
    if not match:
        raise AssertionError("expected remote AWK chronology block")
    return match.group(1)


def classify(source: str, sample: str) -> str:
    result = subprocess.run(
        ["awk", "-v", f"source={source}", remote_awk()],
        input=sample, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class UnboundRestartCauseContract(unittest.TestCase):
    def test_script_parses_and_help_is_offline(self):
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        help_check = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True, text=True,
            timeout=5, check=False,
        )
        self.assertEqual(help_check.returncode, 0, help_check.stderr)
        self.assertIn("--check", help_check.stdout)

    def test_invalid_arguments_never_start_ssh(self):
        for args in ((), ("--check", "--target", "host;rm"),
                     ("--check", "--target"), ("--check", "--port", "0"),
                     ("--check", "--port", "65536"), ("--check", "--port", "abc"),
                     ("--apply",)):
            with self.subTest(args=args):
                env = os.environ | {"PFSENSE_SSH_TARGET": "invalid.invalid"}
                run = subprocess.run(
                    ["bash", str(SCRIPT), *args], capture_output=True,
                    text=True, timeout=5, check=False, env=env,
                )
                self.assertEqual(run.returncode, 2, run.stderr)

    def test_separates_kernel_oom_from_dnsbl_shutdown(self):
        source = (
            "<3>1 2026-10-24T02:10:50.474019+02:00 host kernel - - - "
            "pid 45881 (unbound) killed: failed to reclaim memory token=SECRET\n"
            "<30>1 2026-10-25T00:04:54.724908+02:00 host unbound - - - "
            "[pfBlockerNG]: pfb_unbound.py script exiting private.example\n"
            "<29>1 2026-10-24T23:39:55.370768+02:00 host php-fpm - - - "
            "bind: address already in use password=PRIVATE\n"
            "<29>1 2026-10-24T23:40:04.811083+02:00 host unbound - - - "
            "Restart of unbound 1.26.1.\n"
        )
        output = classify("system", source)
        self.assertIn(
            "event=kernel_oom_unbound timestamp=2026-10-24T02:10:50.474019+02:00",
            output,
        )
        self.assertIn(
            "event=dnsbl_python_exit timestamp=2026-10-25T00:04:54.724908+02:00",
            output,
        )
        self.assertIn(
            "event=unbound_bind_conflict timestamp=2026-10-24T23:39:55.370768+02:00",
            output,
        )
        self.assertIn("event=unbound_restart_notice", output)
        self.assertNotIn("SECRET", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("private.example", output)

    def test_cron_actual_matches_are_signals_not_schedules(self):
        sample = (
            "<78>1 2026-10-24T02:09:00+02:00 fw cron - - - CMD "
            "snort_check_for_rule_updates secret-token\n"
            "<78>1 2026-10-25T00:00:00+02:00 fw cron - - - CMD "
            "pfblockerng.php cron secret-token\n"
            "<78>1 2026-10-25T00:01:00+02:00 fw cron - - - CMD "
            "servicewatchdog_cron secret-token\n"
        )
        out = classify("cron", sample)
        for event in (
            "snort_cron_exec", "pfblockerng_cron_exec", "watchdog_cron_exec",
        ):
            self.assertIn(f"event={event}", out)
        self.assertIn("timestamp=2026-10-25T00:01:00+02:00", out)
        self.assertNotIn("secret-token", out)

    def test_pfblocker_events_cannot_claim_restart_initiator(self):
        sample = (
            "10/25/2026 00:04:52 Restarting DNSBL Service token=SECRET\n"
            "10/25/2026 00:09:01 UPDATE PROCESS ENDED private.example\n"
            "10/25/2026 00:09:10 DNSBL feed PASSED key=HIDDEN\n"
            "no timestamp Restarting DNSBL Service password=PRIVATE\n"
        )
        out = classify("pfblockerng", sample)
        self.assertIn("event=dnsbl_service_restart_marker timestamp=10/25/2026 00:04:52", out)
        self.assertIn("event=pfblockerng_update_end timestamp=10/25/2026 00:09:01", out)
        self.assertIn("timestamp=unknown", out)
        for secret in ("SECRET", "HIDDEN", "PRIVATE", "private.example"):
            self.assertNotIn(secret, out)
        self.assertNotIn("restart_initiator=pfblockerng", out)

    def test_timezone_offset_preserved_across_dst(self):
        events = (
            "<30>1 2026-10-25T02:09:00+02:00 host "
            "unbound Restart of unbound\n"
            "<30>1 2026-10-25T02:09:00+01:00 host "
            "unbound Restart of unbound\n"
        )
        out = classify("system", events)
        self.assertIn("2026-10-25T02:09:00+02:00", out)
        self.assertIn("2026-10-25T02:09:00+01:00", out)

    def test_no_unbounded_collection_or_runtime_mutation(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("BatchMode=yes", code)
        self.assertIn("StrictHostKeyChecking=yes", code)
        self.assertIn("tail -n 4000", code)
        self.assertIn("source=", code)
        self.assertIn("restart_initiator=NOT_PROVEN", code)
        self.assertIn("set -euo pipefail", code)
        self.assertIn("| pfsense_ui_render", code)
        for unsafe in ("restart_service(", "service unbound restart",
                       "pfctl -F", "kill -", "midclt", "curl -d",
                       "unbound-control reload", "cat /conf/config.xml",
                       "service snort stop", "sudo "):
            self.assertNotIn(unsafe, code)

    def test_watchdog_membership_from_xml_without_exposing_config(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split("=== Service Watchdog membership", 1)[1]
        section = section.split("=== Installed pfBlockerNG version", 1)[0]
        matches = re.findall(r"awk '(.*?)' /conf/config[.]xml", section, re.DOTALL)
        self.assertEqual(len(matches), 1)
        payloads = (
            (
                "<pfsense><installedpackages><servicewatchdog>\n"
                "<item><name>unbound</name><secret>DONOTEXPOSE</secret></item>\n"
                "</servicewatchdog></installedpackages></pfsense>\n",
                "watchdog_unbound_membership=LISTED",
            ),
            (
                "<pfsense><installedpackages><servicewatchdog>\n"
                "<item><name>openvpn</name><secret>DONOTEXPOSE</secret></item>\n"
                "</servicewatchdog></installedpackages></pfsense>\n",
                "watchdog_unbound_membership=NOT_LISTED",
            ),
            (
                "<pfsense><installedpackages><pfblockerng/>\n"
                "</installedpackages></pfsense>\n",
                "watchdog_unbound_membership=PACKAGE_SECTION_NOT_OBSERVED",
            ),
        )
        for data, expected in payloads:
            with self.subTest(expected=expected):
                res = subprocess.run(
                    ["awk", matches[0]],
                    input=data, capture_output=True, text=True, check=False,
                )
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn(expected, res.stdout)
                self.assertNotIn("DONOTEXPOSE", res.stdout)

    def test_pfblocker_implementation_probe_is_read_only(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("pfSense-pkg-pfBlockerNG-devel", script)
        self.assertIn("pfSense-pkg-pfBlockerNG", script)
        self.assertIn("pfblocker_implementation_is_execution_proof=no", script)
        self.assertIn("pfb_stop_start_unbound", script)
        self.assertIn("pfb_reload_unbound", script)
        self.assertIn("pfb_validate_unbound", script)
        self.assertIn("grep -Eq", script)
        self.assertNotIn("pkg install", script)
        self.assertNotIn("pkg upgrade", script)
        self.assertNotIn("pkg update", script)

    def test_configd_unbound_actions_are_redacted_when_log_is_present(self):
        sample = (
            "<30>1 2026-10-24T23:39:20+02:00 host configd - - - "
            "Restart Unbound password=PRIVATE\n"
            "<30>1 2026-10-24T23:40:05+02:00 host configd - - - "
            "Reload Unbound token=SECRET\n"
            "<30>1 2026-10-24T23:41:05+02:00 host configd - - - "
            "Reload unrelated package key=PRIVATE\n"
        )
        output = classify("configd", sample)
        self.assertEqual(output.count("event=configd_unbound_action"), 2)
        self.assertIn("timestamp=2026-10-24T23:39:20+02:00", output)
        self.assertIn("timestamp=2026-10-24T23:40:05+02:00", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("SECRET", output)
        self.assertNotIn("unrelated package", output)

    def test_pfblocker_stop_start_marker_without_execution_claim(self):
        events = (
            "10/25/2026 00:04:54 Stopping Unbound Resolver... password=PRIVATE\n"
            "10/25/2026 00:04:56 Starting Unbound Resolver... token=SECRET\n"
            "10/25/2026 00:05:00 Restarting DNSBL Service account=PRIVATE\n"
            "10/25/2026 00:09:01 UPDATE PROCESS ENDED password=PRIVATE\n"
        )
        output = classify("pfblockerng", events)
        for name in (
            "pfblocker_unbound_stop_marker",
            "pfblocker_unbound_start_marker",
            "dnsbl_service_restart_marker",
            "pfblockerng_update_end",
        ):
            self.assertIn(f"event={name}", output)
        self.assertIn("timestamp=10/25/2026 00:04:54", output)
        self.assertNotIn("SECRET", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("restart_initiator=pfblockerng", output)

    def test_static_pfblocker_call_sites_are_not_runtime_proof(self):
        script = SCRIPT.read_text(encoding="utf-8")
        section = script.split(
            "# Static source call sites only", 1,
        )[1].split("pfblocker_possible_call_sites_are_execution_proof=no", 1)[0]
        matches = re.findall(r"\n  awk '(.*?)' \"\$file\"", section, re.DOTALL)
        self.assertEqual(len(matches), 1)
        php = (
            "function pfb_stop_start_unbound($mode) { }\n"
            "function pfb_reload_unbound($mode) {\n"
            "  pfb_stop_start_unbound($mode);\n"
            "}\n"
            "function pfb_update_dnsbl($mode) {\n"
            "  pfb_reload_unbound($mode);\n"
            "}\n"
            "// pfb_stop_start_unbound($secret);\n"
        )
        run = subprocess.run(
            ["awk", matches[0]], input=php,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(
            "pfblocker_possible_call_target=pfb_stop_start_unbound "
            "enclosing_function=pfb_reload_unbound sites=1", run.stdout,
        )
        self.assertIn(
            "pfblocker_possible_call_target=pfb_reload_unbound "
            "enclosing_function=pfb_update_dnsbl sites=1", run.stdout,
        )
        self.assertNotIn("$secret", run.stdout)

    def test_pfblocker_prior_header_timestamp_is_context_not_event(self):
        events = (
            "Loading DNSBL [ 10/25/26 0:00:03 ]\n"
            "Step prepared without raw credentials\n"
            "Stopping Unbound Resolver... token=SECRET\n"
            "Starting Unbound Resolver... token=SECRET\n"
            "Next update [ 10/25/26 0:08:25 ]\n"
            "Restarting DNSBL Service password=PRIVATE\n"
        )
        output = classify("pfblockerng", events)
        self.assertIn(
            "event=pfblocker_unbound_stop_marker timestamp=unknown "
            "preceding_header_local=10/25/26 0:00:03 header_gap_lines=2",
            output,
        )
        self.assertIn(
            "event=pfblocker_unbound_start_marker timestamp=unknown "
            "preceding_header_local=10/25/26 0:00:03 header_gap_lines=3",
            output,
        )
        self.assertIn(
            "event=dnsbl_service_restart_marker timestamp=unknown "
            "preceding_header_local=10/25/26 0:08:25 header_gap_lines=1",
            output,
        )
        self.assertNotIn("SECRET", output)
        self.assertNotIn("PRIVATE", output)

    def test_pfblocker_header_outside_80_lines_is_not_attributed(self):
        events = (
            "Loading DNSBL [ 10/25/26 0:00:03 ]\n"
            + "unrelated long update\n" * 81
            + "Starting Unbound Resolver... token=SECRET\n"
        )
        output = classify("pfblockerng", events)
        self.assertIn("event=pfblocker_unbound_start_marker timestamp=unknown", output)
        self.assertNotIn("preceding_header_local=", output)
        self.assertNotIn("SECRET", output)

    def test_posix_remote_shell_parses_including_nested_awk(self):
        src = SCRIPT.read_text(encoding="utf-8")
        remote = extract_remote_shell(src)
        self.assertIn("set -u", remote)
        self.assertIn("=== Bounded lifecycle and kernel signals", remote)
        result = subprocess.run(
            ["/bin/sh", "-n"], input=remote, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("block's header", remote)

    def test_remote_shell_extraction_accepts_renderer_and_rejects_truncation(self):
        example = (
            "ssh host '/bin/sh -s' <<'REMOTE' | pfsense_ui_render\n"
            "set -u\n"
            "echo safe\n"
            "REMOTE\n"
        )
        self.assertEqual(extract_remote_shell(example), "set -u\necho safe")
        for malformed in (
            "ssh host sh -s <<'REMOTE' | renderer\nset -u\n",
            "ssh host sh -s <<'OTHER' | renderer\nset -u\nOTHER\n",
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(AssertionError, "SSH REMOTE heredoc"):
                    extract_remote_shell(malformed)

    def test_collector_does_not_swallow_awk_failures(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('if ! tail -n 4000 "$file" | awk', code)
        self.assertIn('if ! tail -n 2500 "$file" | awk', code)
        self.assertIn("ERROR: lifecycle_classifier_failed", code)
        self.assertIn("ERROR: feed_log_classifier_failed", code)
        self.assertIn("exit 70", code)
        self.assertNotIn("| tail -35 || true", code)
        self.assertIn("saved[++record_count % 35]", code)

    def test_feed_download_failures_are_redacted_and_classified(self):
        code = SCRIPT.read_text(encoding="utf-8")
        match = re.search(
            r'tail -n 2500 "\$file" \| awk -v family="\$family" '
            r'-v logfile="\$logfile" \'(.*?)\''
            r"\s*;\s*then", code, re.DOTALL,
        )
        self.assertIsNotNone(match)
        events = (
            "Fetching https://private.example/token=SECRET HTTP 404\n"
            "Downloading https://private.example/key=SECRET HTTP 403\n"
            "curl failed: operation timed out https://private.example/SECRET\n"
            "Downloading [ IPinfo databases ] user=SECRET\n"
            "PHP Fatal error: Allowed memory size of 134217728 bytes exhausted\n"
            "Downloading https://private.example/token=SECRET HTTP 429\n"
            "Fetching https://private.example/token=SECRET HTTP 503\n"
        )
        proc = subprocess.run(
            ["awk", "-v", "family=pfblockerng", "-v", "logfile=pfblockerng_main", match.group(1)],
            input=events, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for kind in (
            "http_403_or_404",
            "http_429_rate_limited",
            "http_5xx",
            "download_transport_timeout",
            "asn_ipinfo_retry_signature",
            "php_memory_exhausted",
        ):
            self.assertIn(f"feed_download_signal={kind}", proc.stdout)
        self.assertIn("signal_total=7", proc.stdout)
        self.assertNotIn("SECRET", proc.stdout)
        self.assertNotIn("private.example", proc.stdout)

    def test_feed_artifact_thresholds_match_historical_oom_budget(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("dnsblorig/*", code)
        self.assertIn("warn=16777216; critical=67108864", code)
        self.assertIn("warn=67108864; critical=134217728", code)
        self.assertIn('stat -f', code)
        self.assertIn("size_is_causality_proof=no", code)
        self.assertIn("feed_artifact_status=METADATA_ONLY_NO_LIVE_DOWNLOAD", code)
        self.assertIn("tr -c 'A-Za-z0-9._-'", code)

    def test_full_remote_shell_executes_classifier_with_fixture(self):
        # The old tests invoked AWK alone and missed a shell-quoting defect.
        source = SCRIPT.read_text(encoding="utf-8")
        remote = extract_remote_shell(source)
        begin = remote.index("for file in /var/log/system.log")
        end = remote.index("echo '=== Feed download errors", begin)
        loop = remote[begin:end]
        loop = re.sub(
            r"^for file in .*?; do",
            'for file in "$1"; do',
            loop, count=1, flags=re.DOTALL,
        )
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-shell-") as td:
            logfile = Path(td) / "system.log"
            logfile.write_text(
                "<3>1 2026-10-24T02:10:50.474019+02:00 fw kernel - - - "
                "pid 45881 (unbound) killed: failed to reclaim memory "
                "token=DO_NOT_PRINT\n",
                encoding="utf-8",
            )
            run = subprocess.run(
                ["/bin/sh", "-c", loop, "sh", str(logfile)],
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("event=kernel_oom_unbound", run.stdout)
            self.assertIn("timestamp=2026-10-24T02:10:50.474019+02:00", run.stdout)
            self.assertNotIn("DO_NOT_PRINT", run.stdout)

            broken = loop.replace(
                "    function stamp(line, s) {",
                "    THIS TOKEN IS INVALID AWK;\n    function stamp(line, s) {",
            )
            failure = subprocess.run(
                ["/bin/sh", "-c", broken, "sh", str(logfile)],
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertNotEqual(failure.returncode, 0)
            self.assertIn("ERROR: lifecycle_classifier_failed", failure.stdout)


if __name__ == "__main__":
    unittest.main()
