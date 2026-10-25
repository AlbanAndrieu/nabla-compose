"""Read-only and private-by-default Unbound snapshot capture contracts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/capture-unbound-snapshot.sh"
VALID_REPORT = (
    "pfSense_time=2026-10-26T00:12:48+0100\n"
    "unbound_pid=2611 started_local=Mon_Oct_26_00:04:32_2026 rss_kib=133164\n"
    "unbound_control=REACHABLE\n"
    "=== End of read-only Unbound restart triage ===\n"
)


def run_capture(mock_report: str = VALID_REPORT, collector_exit: int = 0):
    with tempfile.TemporaryDirectory(prefix="unbound-capture-") as temp:
        root = Path(temp)
        scripts = root / "scripts" / "pfsense"
        scripts.mkdir(parents=True)
        capture = scripts / SCRIPT.name
        shutil.copyfile(SCRIPT, capture)
        collector = scripts / "diagnose-unbound-restart-cause.sh"
        collector.write_text(
            "#!/bin/bash\n"
            "if [[ \"$1\" != --check ]]; then exit 2; fi\n"
            "printf '%s\\n' \"$SNAPSHOT_MOCK_REPORT\"\n"
            f"exit {collector_exit}\n", encoding="utf-8",
        )
        state = root / "snapshots"
        env = dict(os.environ)
        env["PFSENSE_UNBOUND_SNAPSHOT_DIR"] = str(state)
        env["SNAPSHOT_MOCK_REPORT"] = mock_report.rstrip("\n")
        proc = subprocess.run(
            ["bash", str(capture), "--check"],
            env=env, text=True, capture_output=True, check=False, timeout=5,
        )
        files = list(state.glob("*.log")) if state.exists() else []
        saved = files[0].read_text(encoding="utf-8") if len(files) == 1 else ""
        permissions = (
            stat.S_IMODE(files[0].stat().st_mode),
            stat.S_IMODE(state.stat().st_mode),
        ) if len(files) == 1 else None
        return proc, files, saved, permissions


class UnboundSnapshotCaptureContract(unittest.TestCase):
    def test_bash_parser_and_usage_are_offline(self):
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        help_text = subprocess.run(
            ["bash", str(SCRIPT), "--help"], text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(help_text.returncode, 0, help_text.stderr)
        self.assertIn("--check", help_text.stdout)

    def test_valid_capture_is_private_and_readonly(self):
        proc, files, text, mode = run_capture()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(files), 1)
        self.assertEqual(mode, (0o600, 0o700))
        self.assertIn("unbound_pid=2611", text)
        self.assertIn("snapshot_saved=", proc.stdout)
        self.assertIn("snapshot_scope=WORKSTATION_ONLY_REDACTED_READONLY", proc.stdout)

    def test_failed_or_incomplete_capture_is_deleted(self):
        for report, code in (
            (VALID_REPORT, 1),
            ("pfSense_time=2026-10-26T00:12:48+0100", 0),
            (VALID_REPORT + "ERROR: feed_log_classifier_failed", 0),
            (VALID_REPORT + "EVIDENCE INCOMPLETE", 0),
        ):
            with self.subTest(report=report[-35:], exit_code=code):
                proc, files, _, _ = run_capture(report, code)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(files, [])

    def test_arguments_fail_before_ssh(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--apply"],
            text=True, capture_output=True, check=False, timeout=5,
        )
        self.assertEqual(result.returncode, 2)

    def test_source_never_mutates_pfsense(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "service unbound restart", "unbound-control reload",
            "pfctl -F", "service snort restart", "sudo ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("umask 077", source)
        self.assertIn("PFSENSE_OUTPUT=verbose bash", source)
        self.assertIn("chmod 700", source)


if __name__ == "__main__":
    unittest.main()
