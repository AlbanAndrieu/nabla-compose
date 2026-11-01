"""Hermetic contract tests for one-shot Talos service state/health checks."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/talos/validate-cluster.sh"


class TalosServiceStatusTests(unittest.TestCase):
    @staticmethod
    def function_source() -> str:
        text = SCRIPT.read_text()
        start = text.index("check_talos_service() {")
        return text[start:text.index("\n}\n", start) + 2]

    def invoke(self, response: str, code: int = 0) -> tuple[subprocess.CompletedProcess[str], int]:
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "calls"
            bash = f"""
set -euo pipefail
fail() {{ printf '%s\\n' "$*" >&2; return 23; }}
talosctl() {{
  printf 'called\\n' >> "${{COUNT_FILE}}"
  printf '%s\\n' "${{SERVICE_RESPONSE}}"
  return "${{SERVICE_EXIT}}"
}}
{self.function_source()}
check_talos_service 172.17.0.50 kubelet
"""
            env = dict(os.environ, COUNT_FILE=str(counter), SERVICE_RESPONSE=response,
                       SERVICE_EXIT=str(code))
            result = subprocess.run(  # noqa: S603 - repository-owned Bash function only
                [shutil.which("bash") or "bash", "-c", bash],
                text=True, capture_output=True, env=env, timeout=5, check=False,
            )
            count = len(counter.read_text().splitlines()) if counter.exists() else 0
            return result, count

    def test_service_read_once_and_healthy(self) -> None:
        result, calls = self.invoke("STATE Running\nHEALTH OK")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, 1)

    def test_unhealthy_and_stopped_both_fail_closed(self) -> None:
        for report in ("STATE Running\nHEALTH FAIL", "STATE Stopped\nHEALTH OK"):
            with self.subTest(report=report):
                result, calls = self.invoke(report)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, 1)

    def test_failed_talos_command_is_not_accepted(self) -> None:
        result, calls = self.invoke("STATE Running\nHEALTH OK", code=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, 1)
        self.assertIn("cannot query kubelet", result.stderr)


if __name__ == "__main__":
    unittest.main()
