"""Offline tests for the snapshot-task reconciliation (fakeroot + stubbed midclt/zfs)."""

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
POLICY = json.loads((ROOT / "config/truenas/snapshot-tasks.json").read_text(encoding="utf-8"))
LIFETIME_UNITS = {"HOUR", "DAY", "WEEK", "MONTH", "YEAR"}


def expanded_tasks() -> list[dict]:
    """Mirror of the jq expansion in reconcile-snapshot-tasks.sh."""
    schedules = POLICY["schedules"]
    return [
        {"dataset": dataset, "recursive": True, **schedules[name]}
        for policy_class in POLICY["classes"]
        for dataset in policy_class["datasets"]
        for name in policy_class["schedules"]
    ]


class SnapshotPolicyTests(unittest.TestCase):
    def test_backup_policy_is_daily_and_weekly(self):
        backup = {(t["lifetime_value"], t["lifetime_unit"]) for t in expanded_tasks() if t["dataset"] == "cpool/backup"}
        self.assertEqual(backup, {(14, "DAY"), (8, "WEEK")})

    def test_classes_follow_the_approved_policy(self):
        lifetimes = {
            policy_class["name"]: sorted(
                (POLICY["schedules"][name]["lifetime_value"], POLICY["schedules"][name]["lifetime_unit"])
                for name in policy_class["schedules"]
            )
            for policy_class in POLICY["classes"]
        }
        self.assertEqual(lifetimes["critical"], [(30, "DAY"), (48, "HOUR")])
        self.assertEqual(lifetimes["databases"], [(7, "DAY"), (24, "HOUR")])
        self.assertEqual(lifetimes["backup-targets"], [(8, "WEEK"), (14, "DAY")])
        self.assertEqual(lifetimes["app-state"], [(12, "WEEK"), (30, "DAY")])
        self.assertEqual(lifetimes["user-data"], [(12, "MONTH"), (30, "DAY")])

    def test_every_dataset_has_one_class_and_never_conflicts_with_no_snapshot(self):
        datasets = [d for policy_class in POLICY["classes"] for d in policy_class["datasets"]]
        self.assertEqual(len(datasets), len(set(datasets)))
        excluded = {entry["dataset"] for entry in POLICY["noSnapshot"]}
        self.assertFalse(set(datasets) & excluded)
        self.assertIn("cpool/ix-apps/docker", excluded)
        # Re-creatable data (owner decision 10/11): rare, bounded points only.
        classes = {c["name"]: c for c in POLICY["classes"]}
        self.assertEqual(classes["resync-shortcut"]["datasets"], ["cpool/bitcoind"])
        self.assertEqual(classes["resync-shortcut"]["schedules"], ["monthly-1m"])
        self.assertEqual(classes["recreatable"]["schedules"], ["monthly-3m", "yearly-1y"])
        self.assertIn("cpool/nexus3", classes["recreatable"]["datasets"])
        self.assertTrue(all(entry["reason"] for entry in POLICY["noSnapshot"]))

    def test_every_task_is_bounded_and_unique(self):
        tasks = expanded_tasks()
        keys = [(t["dataset"], t["naming_schema"]) for t in tasks]
        self.assertEqual(len(keys), len(set(keys)))
        for task in tasks:
            self.assertGreater(task["lifetime_value"], 0)
            self.assertIn(task["lifetime_unit"], LIFETIME_UNITS)
            self.assertFalse(task["allow_empty"])
            self.assertIn("%Y-%m-%d_%H-%M", task["naming_schema"])


@unittest.skipUnless(shutil.which("fakeroot") and shutil.which("jq"), "fakeroot and jq required")
class ReconcileSnapshotTasksTests(unittest.TestCase):
    def run_script(self, existing, *args, approved=False, datasets=("cpool", "cpool/backup")):
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
            zfs = bin_dir / "zfs"
            zfs.write_text("#!/usr/bin/env bash\nprintf '%s\\n' " + " ".join(datasets) + "\n")
            zfs.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "NO_COLOR": "1"}
            env.pop("NABLA_SNAPSHOT_APPLY_APPROVED", None)
            if approved:
                env["NABLA_SNAPSHOT_APPLY_APPROVED"] = "yes"
            result = subprocess.run(
                ["fakeroot", "bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False
            )
            calls = log.read_text().split() if log.exists() else []
        return result, calls

    def test_plan_creates_nothing(self):
        result, calls = self.run_script([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pool.snapshottask.create", calls)
        self.assertIn("missing: cpool/backup auto-daily", result.stdout + result.stderr)

    def test_apply_needs_second_approval(self):
        result, calls = self.run_script([], "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_apply_creates_only_missing_tasks_on_existing_datasets(self):
        backup_daily = next(t for t in expanded_tasks() if t["dataset"] == "cpool/backup")
        result, calls = self.run_script([{**backup_daily, "id": 1}], "--apply", approved=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("pool.snapshottask.create"), 1)
        output = result.stdout + result.stderr
        self.assertIn("present: cpool/backup auto-daily", output)
        self.assertIn("absent: cpool/vaultwarden", output)

    def test_recursive_task_covering_no_snapshot_dataset_is_reported(self):
        parent = {
            "id": 9,
            "dataset": "cpool",
            "recursive": True,
            "exclude": ["cpool/ollama"],
            "naming_schema": "auto-%Y-%m-%d_%H-%M",
            "lifetime_value": 2,
            "lifetime_unit": "WEEK",
            "schedule": {"minute": "0", "hour": "0", "dom": "*", "month": "*", "dow": "*"},
        }
        result, calls = self.run_script(
            [parent], datasets=("cpool", "cpool/backup", "cpool/bitcoind", "cpool/ollama")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pool.snapshottask.create", calls)
        output = result.stdout + result.stderr
        self.assertIn("task 9 on cpool covers cpool/bitcoind", output)
        self.assertNotIn("covers cpool/ollama", output)


if __name__ == "__main__":
    unittest.main()
