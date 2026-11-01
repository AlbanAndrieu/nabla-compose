"""Offline tests for the snapshot-task reconciliation (fakeroot + stubbed midclt)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-snapshot-tasks.sh"
DESIRED = json.loads((ROOT / "config/truenas/snapshot-tasks.json").read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("fakeroot") and shutil.which("jq"), "fakeroot and jq required")
class ReconcileSnapshotTasksTests(unittest.TestCase):
    def run_script(self, existing, *args, approved=False):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            log = bin_dir / "calls.log"
            stub = bin_dir / "midclt"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                + textwrap.dedent(
                    f"""\
                    echo "$2" >> {log}
                    [[ "$2" == pool.snapshottask.query ]] && echo '{json.dumps(existing)}'
                    exit 0
                    """
                )
            )
            stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "NO_COLOR": "1"}
            env.pop("NABLA_SNAPSHOT_APPLY_APPROVED", None)
            if approved:
                env["NABLA_SNAPSHOT_APPLY_APPROVED"] = "yes"
            result = subprocess.run(
                ["fakeroot", "bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False
            )
            calls = log.read_text().split() if log.exists() else []
        return result, calls

    def test_backup_policy_is_daily_and_weekly(self):
        self.assertEqual({(t["dataset"], t["lifetime_value"], t["lifetime_unit"]) for t in DESIRED},
                         {("cpool/backup", 14, "DAY"), ("cpool/backup", 8, "WEEK")})

    def test_plan_creates_nothing(self):
        result, calls = self.run_script([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pool.snapshottask.create", calls)
        self.assertIn("missing: cpool/backup auto-daily", result.stdout + result.stderr)

    def test_apply_needs_second_approval(self):
        result, calls = self.run_script([], "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_apply_creates_only_missing_tasks(self):
        result, calls = self.run_script([{**DESIRED[0], "id": 1}], "--apply", approved=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("pool.snapshottask.create"), 1)
        self.assertIn("present: cpool/backup auto-daily", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
