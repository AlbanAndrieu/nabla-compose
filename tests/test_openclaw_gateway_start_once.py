"""Offline contracts for the one-shot OpenClaw Gateway start protocol."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/start-openclaw-gateway-once.sh"


class OpenClawOneShotStart(unittest.TestCase):
    def test_bash_syntax(self):
        completed = subprocess.run(["bash", "-n", str(SCRIPT)],
                                   capture_output=True, timeout=8, check=False)
        self.assertEqual(completed.returncode, 0)

    def test_strictly_one_explicit_start_no_restart_or_fix(self):
        lines = [line.strip() for line in SCRIPT.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        starts = [line for line in lines if "systemctl --user start " in line]
        self.assertEqual(len(starts), 1)
        executable = "\n".join(lines)
        for unsafe in ("systemctl --user restart", "systemctl --user reset-failed",
                       "openclaw update", "npm install", "doctor --fix",
                       "backup-openclaw.sh", "rm -rf", "kill -9"):
            self.assertNotIn(unsafe, executable)
        self.assertIn('--select-installed-plan', executable)
        self.assertIn('fuser -s', executable)
        self.assertIn('diagnose-openclaw-gateway-service-failure.py', executable)
        self.assertIn('diagnose-openclaw-gateway-readiness.py', executable)

    def test_missing_operator_flag_is_nonmutating(self):
        run = subprocess.run(["bash", str(SCRIPT)],
                             capture_output=True, timeout=8, check=False)
        self.assertEqual(run.returncode, 2)
        self.assertIn(b"usage:", run.stdout)

    def test_script_does_not_publish_raw_systemctl_errors(self):
        self.assertIn('systemctl --user start "${UNIT}" >/dev/null 2>&1;',
                      SCRIPT.read_text())


if __name__ == "__main__":
    unittest.main()
