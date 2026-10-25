"""Offline regression tests for correlated, bounded Unbound restart evidence."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/compare-unbound-snapshots.py"
spec = importlib.util.spec_from_file_location("unbound_compare", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

HASH_A = "a" * 64
HASH_B = "b" * 64
BEFORE = (
    "pfSense_time=2026-10-25T23:56:01+0100\n"
    "unbound_pid=19252 started_local=Sun_Oct_25_22:46:18_2026 rss_kib=128476\n"
    "unbound_control=REACHABLE\n"
    f"config_fingerprint=unbound_config size_bytes=2289 sha256={HASH_A}\n"
    f"config_fingerprint=dnsbl_legacy_ini size_bytes=355 sha256={HASH_B}\n"
    "config_fingerprint=dnsbl_python_ini status=UNAVAILABLE\n"
)
AFTER = (
    "pfSense_time=2026-10-26T00:12:48+0100\n"
    "unbound_pid=2611 started_local=Mon_Oct_26_00:04:32_2026 rss_kib=133164\n"
    "unbound_control=REACHABLE\n"
    f"config_fingerprint=unbound_config size_bytes=2289 sha256={HASH_A}\n"
    f"config_fingerprint=dnsbl_legacy_ini size_bytes=355 sha256={HASH_B}\n"
    "config_fingerprint=dnsbl_python_ini status=UNAVAILABLE\n"
    "log_family=system readable=yes\n"
    "Historical kernel OOM victim=unbound "
    "timestamp=2026-10-25T22:12:35.557637+01:00\n"
    "signal_source=resolver event=dnsbl_python_exit "
    "timestamp=2026-10-26T00:04:30.252104+01:00\n"
    "signal_source=pfblockerng event=pfblocker_unbound_stop_marker "
    "timestamp=unknown preceding_header_local=10/26/26 00:04:25 header_gap_lines=2\n"
    "signal_source=pfblockerng event=pfblocker_unbound_start_marker "
    "timestamp=unknown preceding_header_local=10/26/26 00:04:37 header_gap_lines=0\n"
    "private-feed.example token=DO_NOT_OUTPUT\n"
)


class UnboundSnapshotCompareContract(unittest.TestCase):
    def test_real_midnight_pid_change_correlates_without_kernel_oom(self):
        report = module.compare(BEFORE, AFTER)
        self.assertEqual(report["unbound_pid_changed"], "yes")
        self.assertEqual(report["unbound_start_in_window"], "yes")
        self.assertEqual(report["unbound_config_hash"], "MATCH")
        self.assertEqual(report["dnsbl_legacy_ini_hash"], "MATCH")
        self.assertEqual(report["dnsbl_python_ini_hash"], "UNKNOWN_MISSING_EVIDENCE")
        self.assertEqual(report["pfblocker_stop_header_in_window"], "yes")
        self.assertEqual(report["pfblocker_start_header_in_window"], "yes")
        self.assertEqual(report["dnsbl_python_exit_in_window"], "yes")
        self.assertEqual(
            report["restart_assessment"],
            "PF_BLOCKER_DNSBL_SEQUENCE_CORRELATES_WITH_PID_CHANGE",
        )
        self.assertEqual(report["kernel_oom_since_baseline"], "NONE_IN_BOUNDED_VISIBLE_LOGS")
        self.assertEqual(report["kernel_oom_count_visible_since_baseline"], "0")
        self.assertEqual(report["after_unbound_control"], "REACHABLE")

    def test_new_oom_prevents_dnsbl_only_attribution(self):
        after = AFTER + (
            "Historical kernel OOM victim=unbound "
            "timestamp=2026-10-26T00:04:31.000000+01:00\n"
        )
        report = module.compare(BEFORE, after)
        self.assertEqual(report["kernel_oom_since_baseline"], "NEW_KERNEL_OOM_VISIBLE")
        self.assertEqual(report["unbound_oom_count_visible_since_baseline"], "1")
        self.assertEqual(
            report["restart_assessment"],
            "RESTART_WITH_MIXED_OR_INCOMPLETE_CAUSE_SIGNALS",
        )

    def test_no_pid_change_does_not_claim_restart(self):
        after = AFTER.replace(
            "unbound_pid=2611", "unbound_pid=19252"
        )
        report = module.compare(BEFORE, after)
        self.assertEqual(report["unbound_pid_changed"], "no")
        self.assertEqual(report["restart_assessment"], "NO_PID_CHANGE_IN_THIS_INTERVAL")

    def test_missing_system_log_does_not_claim_no_oom(self):
        after = AFTER.replace("log_family=system readable=yes\n", "")
        result = module.compare(BEFORE, after)
        self.assertEqual(
            result["kernel_oom_since_baseline"],
            "UNKNOWN_SYSTEM_LOG_NOT_VERIFIED",
        )
        self.assertEqual(
            result["restart_assessment"],
            "RESTART_WITH_MIXED_OR_INCOMPLETE_CAUSE_SIGNALS",
        )

    def test_dst_crossing_does_not_invent_header_offset(self):
        before = BEFORE.replace(
            "2026-10-25T23:56:01+0100", "2026-10-25T01:56:01+0200"
        )
        after = AFTER.replace(
            "2026-10-26T00:12:48+0100", "2026-10-25T02:12:48+0100"
        )
        result = module.compare(before, after)
        self.assertEqual(result["pfblocker_stop_header_in_window"], "no_or_unverifiable")
        self.assertNotEqual(
            result["restart_assessment"],
            "PF_BLOCKER_DNSBL_SEQUENCE_CORRELATES_WITH_PID_CHANGE",
        )

    def test_cli_redacts_inputs_and_is_readonly(self):
        with tempfile.TemporaryDirectory(prefix="unbound-diff-") as tmp:
            before = Path(tmp) / "before.log"
            after = Path(tmp) / "after.log"
            before.write_text(BEFORE, encoding="utf-8")
            after.write_text(AFTER, encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--before", str(before), "--after", str(after),
                ],
                text=True, capture_output=True, check=False, timeout=5,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("unbound_pid_before=19252", run.stdout)
            self.assertIn("unbound_pid_after=2611", run.stdout)
            self.assertNotIn("DO_NOT_OUTPUT", run.stdout)
            self.assertNotIn("private-feed.example", run.stdout)
            self.assertNotIn(HASH_A, run.stdout)
            self.assertEqual(before.read_text(encoding="utf-8"), BEFORE)
            self.assertEqual(after.read_text(encoding="utf-8"), AFTER)

    def test_cli_distinguishes_missing_empty_and_same_capture(self):
        with tempfile.TemporaryDirectory(prefix="unbound-input-errors-") as tmp:
            a = Path(tmp) / "a.log"
            b = Path(tmp) / "b.log"
            missing = Path(tmp) / "not-created.log"
            a.write_text(BEFORE, encoding="utf-8")
            b.write_text("", encoding="utf-8")

            def run(baseline, later):
                return subprocess.run(
                    [
                        sys.executable, str(SCRIPT),
                        "--before", str(baseline), "--after", str(later),
                    ],
                    text=True, capture_output=True, timeout=5, check=False,
                )

            for baseline, later, reason in (
                (missing, a, "before_file_missing"),
                (a, missing, "after_file_missing"),
                (a, b, "after_file_empty"),
                (a, a, "reports_same_timestamp"),
            ):
                with self.subTest(reason=reason):
                    output = run(baseline, later)
                    self.assertEqual(output.returncode, 2)
                    self.assertIn("reason=" + reason, output.stderr)
                    self.assertIn("hint=", output.stderr)
                    self.assertNotIn(str(tmp), output.stderr)
                    self.assertNotIn(HASH_A, output.stderr)

    def test_cli_distinguishes_unrecognized_reports_and_reversed_order(self):
        with tempfile.TemporaryDirectory(prefix="unbound-input-errors-") as tmp:
            a, b = Path(tmp) / "a.log", Path(tmp) / "b.log"
            a.write_text(BEFORE, encoding="utf-8")
            for data, reason in (
                ("some unrelated log", "after_missing_pfSense_time"),
                (BEFORE.replace("unbound_pid=19252", "unbound_pid=unavailable"),
                 "after_missing_unbound_pid"),
                (BEFORE, "reports_same_timestamp"),
            ):
                with self.subTest(reason=reason):
                    b.write_text(data, encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT),
                         "--before", str(a), "--after", str(b)],
                        text=True, capture_output=True, timeout=5, check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("reason=" + reason, result.stderr)

            b.write_text(AFTER, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--before", str(b),
                 "--after", str(a)],
                text=True, capture_output=True, timeout=5, check=False,
            )
            self.assertIn("reason=reports_out_of_order", result.stderr)

    def test_incomplete_collector_report_rejected(self):
        with tempfile.TemporaryDirectory(prefix="unbound-input-errors-") as tmp:
            a, b = Path(tmp) / "a.log", Path(tmp) / "b.log"
            a.write_text(BEFORE, encoding="utf-8")
            b.write_text(AFTER + "ERROR: feed_log_classifier_failed\\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--before", str(a),
                 "--after", str(b)],
                text=True, capture_output=True, timeout=5, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("reason=after_collector_incomplete", result.stderr)

    def test_missing_or_reversed_evidence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "reports_out_of_order"):
            module.compare(AFTER, BEFORE)
        with self.assertRaisesRegex(ValueError, "after_missing_unbound_pid"):
            module.compare(BEFORE, AFTER.replace("unbound_pid=2611", "unbound_pid=x"))
        with tempfile.TemporaryDirectory(prefix="unbound-diff-") as tmp:
            path = Path(tmp) / "before"
            link = Path(tmp) / "symlink"
            path.write_text(BEFORE, encoding="utf-8")
            link.symlink_to(path)
            with self.assertRaisesRegex(ValueError, "before_file_is_symlink"):
                module.load_report(str(link))


if __name__ == "__main__":
    unittest.main()
