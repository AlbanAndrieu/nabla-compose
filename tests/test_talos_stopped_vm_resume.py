"""Offline TrueNAS Talos VM resume contracts; no actual VM operations."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/resume-stopped-talos-vms.py"
spec = importlib.util.spec_from_file_location("resume_stopped_talos", SCRIPT)
assert spec is not None and spec.loader is not None
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def fixture(state="STOPPED"):
    return [
        {"id": 6, "name": "taloscp01", "autostart": True, "status": {"state": state}},
        {"id": 7, "name": "taloswk01", "autostart": True, "status": {"state": state}},
        {"id": 8, "name": "taloswk02", "autostart": True, "status": {"state": state}},
    ]


class TalosStoppedVMTest(unittest.TestCase):
    def test_expected_names_order(self):
        self.assertEqual(MODULE.VM_NAMES, ("taloscp01", "taloswk01", "taloswk02"))

    def test_synthetic_stopped_vms_do_not_start(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vm.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check", "--query-json", str(path)],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("READ_ONLY", result.stdout)
        self.assertIn("taloscp01", result.stdout)

    def test_ambiguous_and_transitional_states_refused(self):
        for data in (fixture() + [fixture()[0]], fixture("STARTING"), []):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    MODULE.inventory(data)

    def test_vm_start_timeout_followed_by_running_is_not_retried(self):
        stopped = MODULE.inventory(fixture())[0]
        with patch.object(MODULE.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("vm.start", 180)) as run:
            with patch.object(MODULE, "midclt",
                              return_value=json.dumps(fixture("RUNNING"))) as query:
                self.assertTrue(MODULE.start_and_observe(stopped))
        self.assertEqual(run.call_count, 1)
        self.assertGreaterEqual(query.call_count, 1)

    def test_vm_start_timeout_without_running_does_not_repeat_start(self):
        stopped = MODULE.inventory(fixture())[0]
        with patch.object(MODULE.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("vm.start", 180)) as run:
            with patch.object(MODULE, "midclt",
                              return_value=json.dumps(fixture("STOPPED"))):
                with patch.object(MODULE.time, "sleep", return_value=None):
                    self.assertFalse(MODULE.start_and_observe(stopped))
        self.assertEqual(run.call_count, 1)

    def test_vm_state_polling_does_not_guess_health_or_cluster(self):
        with patch.object(MODULE, "midclt",
                          return_value=json.dumps(fixture("RUNNING"))):
            self.assertEqual(MODULE.wait_for_vm_state("taloscp01"), "RUNNING")
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Talos/etcd not yet verified", source)
        self.assertNotIn("talosctl upgrade", source)

    def test_start_requires_explicit_ack_and_live_inventory(self):
        for args in (["--start"], ["--start", "--query-json", "/tmp/invalid"]):
            with self.subTest(args=args):
                run = subprocess.run([sys.executable, str(SCRIPT), *args],
                                     capture_output=True, text=True, check=False)
                self.assertEqual(run.returncode, 2)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('"vm.stop"', source)
        self.assertNotIn("talosctl upgrade", source)
        self.assertNotIn("etcd reset", source)


if __name__ == "__main__":
    unittest.main()
