"""Offline contracts for read-only pfSense Unbound lifecycle provenance."""
from pathlib import Path
import os
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/diagnose-unbound-restart-cause.sh"


def remote_awk() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(
        r'tail -n 4000 "\$file" \| awk -v source="\$source" \'(.*?)\''
        r" \| tail -35", source, re.DOTALL,
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


if __name__ == "__main__":
    unittest.main()
