"""All read-only OpenClaw checks must run even if an earlier probe fails."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/workstation/openclaw-recovery-readonly.sh'


class ReadonlyRunnerContracts(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(['bash', '-n', str(SOURCE)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)

    def test_independent_checks_and_failure_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'scripts/workstation/openclaw-recovery-readonly.sh'
            target.parent.mkdir(parents=True)
            shutil.copyfile(SOURCE, target)
            fake = root / 'bin/python3'
            fake.parent.mkdir()
            fake.write_text('#!/bin/sh\necho simulated:$1\ncase "$1" in *check-openclaw-runtime-alignment.py) exit 2;; esac\nexit 0\n')
            fake.chmod(0o755)
            environment = {**os.environ, 'PATH': str(fake.parent) + ':' + os.environ['PATH']}
            result = subprocess.run(['bash', str(target)], env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout.count('simulated:'), 5)
            self.assertIn('probe=litellm_dual_logs result=completed', result.stdout)
            self.assertIn('probe_failures=1', result.stdout)
            fake.write_text('#!/bin/sh\necho simulated:$1\nexit 0\n')
            ok = subprocess.run(['bash', str(target)], env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(ok.returncode, 0)
            self.assertIn('probe_failures=0', ok.stdout)
            env_sudo = {**environment, 'OPENCLAW_TRUENAS_LOG_SUDO': '1'}
            sudo = subprocess.run(['bash', str(target)], env=env_sudo,
                                  capture_output=True, text=True, check=False)
            self.assertEqual(sudo.returncode, 0)
            self.assertIn('--truenas-sudo-logs', sudo.stdout)


if __name__ == '__main__':
    unittest.main()
