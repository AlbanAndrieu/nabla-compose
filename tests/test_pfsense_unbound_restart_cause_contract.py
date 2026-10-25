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


if __name__ == "__main__":
    unittest.main()
