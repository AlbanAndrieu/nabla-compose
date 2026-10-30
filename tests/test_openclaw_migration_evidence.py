"""Hermetic contracts: independent probes and no mutating CLI actions."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import shutil

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/workstation/openclaw-migration-evidence.sh"


class MigrationEvidence(unittest.TestCase):
    def test_shell_syntax_and_no_mutating_recipes(self):
        self.assertEqual(subprocess.run(["bash","-n",str(SOURCE)],capture_output=True).returncode,0)
        raw=SOURCE.read_text()
        for forbidden in ("openclaw-truenas-virtual-keys-apply",
                          "openclaw-cron-session-maintenance-apply",
                          "openclaw-morning-briefing-apply",
                          "--smoke-model"):
            self.assertNotIn(forbidden,raw)

    def test_independent_probes_and_nonzero_on_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"scripts/workstation/openclaw-migration-evidence.sh"
            target.parent.mkdir(parents=True)
            shutil.copyfile(SOURCE,target)
            fake=root/"bin/just"
            fake.parent.mkdir()
            fake.write_text('#!/bin/sh\nprintf "mock:%s\\n" "$1"\n'
                            'case "$1" in openclaw-truenas-tunnel-check) exit 2;; esac\n'
                            'exit 0\n')
            fake.chmod(0o755)
            python=root/"bin/python3"
            python.write_text("#!/bin/sh\nexit 0\n")
            python.chmod(0o755)
            env={**os.environ,"PATH":str(fake.parent)+":"+os.environ.get("PATH","")}
            result=subprocess.run(["bash",str(target),"--diagnose"],
                                  env=env,check=False,text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertIn("truenas_tunnel unverified_or_failed",result.stdout)
            self.assertIn("PROBE digest_top completed",result.stdout)
            self.assertIn("unverified_or_failed=1",result.stdout)

    def test_invalid_mode_never_calls_just(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"just"
            target.write_text('#!/bin/sh\nprintf "INVOKED"\n')
            target.chmod(0o755)
            r=subprocess.run(["bash",str(SOURCE),"--apply"],
                             capture_output=True,text=True,check=False,
                             env={**os.environ,"PATH":tmp+":"+os.environ["PATH"]})
            self.assertEqual(r.returncode,2)
            self.assertNotIn("INVOKED",r.stdout)


if __name__=="__main__":
    unittest.main()
