"""Offline checks for the Prometheus SIGHUP reload: fake docker/curl, no host access."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reload-prometheus-rules.sh"

DOCKER = """#!/bin/sh
echo "$*" >> "$CALLS"
case "$1" in
  ps) echo abc123 ;;
  exec) case "$*" in
    *promtool*) exit "$PROMTOOL_RC" ;;
    *stat*) echo 1000; echo "$FILES_MTIME" ;;
  esac ;;
  kill) echo 2000 > "$RELOAD_FILE" ;;
esac
"""
CURL = """#!/bin/sh
printf '{"data":{"result":[{"value":[0,"%s"]}]}}' "$(cat "$RELOAD_FILE")"
"""


@unittest.skipUnless(shutil.which("jq"), "jq is required by the script")
class ReloadPrometheusRulesTest(unittest.TestCase):
    def run_script(self, mode: str, files_mtime: int, promtool_rc: int = 0):
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            for name, body in (("docker", DOCKER), ("curl", CURL)):
                (tmp / name).write_text(body, encoding="utf-8")
                (tmp / name).chmod(0o755)
            (tmp / "reload").write_text("1500\n", encoding="utf-8")
            env = os.environ | {
                "PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}",
                "CALLS": str(tmp / "calls"),
                "RELOAD_FILE": str(tmp / "reload"),
                "FILES_MTIME": str(files_mtime),
                "PROMTOOL_RC": str(promtool_rc),
            }
            result = subprocess.run(["bash", str(SCRIPT), mode], env=env, capture_output=True,
                                    text=True, timeout=60, check=False)
            calls = (tmp / "calls").read_text(encoding="utf-8")
            return result, calls

    def test_in_sync_never_signals(self) -> None:
        for mode in ("check", "apply"):
            result, calls = self.run_script(mode, files_mtime=1200)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("reload_needed=no", result.stdout)
            self.assertNotIn("kill", calls)

    def test_stale_check_fails_and_apply_reloads(self) -> None:
        result, calls = self.run_script("check", files_mtime=1800)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reload_needed=yes", result.stdout)
        self.assertNotIn("kill", calls)

        result, calls = self.run_script("apply", files_mtime=1800)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("kill -s HUP abc123", calls)
        self.assertIn("OK: Prometheus reloaded", result.stdout)

    def test_invalid_rules_are_never_signalled(self) -> None:
        result, calls = self.run_script("apply", files_mtime=1800, promtool_rc=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("promtool check config failed", result.stdout)
        self.assertNotIn("kill", calls)


if __name__ == "__main__":
    unittest.main()
