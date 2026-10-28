"""Offline contracts for scoped, no-leak OpenClaw session maintenance."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-cron-session-maintenance.py"
spec = importlib.util.spec_from_file_location("cron_cleanup", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def report(agent="cron"):
    return json.dumps({"allAgents": False, "stores": [
        {"agentId": agent, "storePath": "DO-NOT-LEAK", "beforeCount": 21,
         "afterCount": 3, "pruned": 18, "capped": 0}]}).encode()


class CronCleanupTests(unittest.TestCase):
    def test_parse_scoped_counts_without_private_paths(self):
        result = mod.summarize(report(), dry_run=True)
        self.assertEqual(result["state"], "structured")
        self.assertEqual(result["counters"]["beforeCount"], 21)
        self.assertNotIn("DO-NOT-LEAK", json.dumps(result))

    def test_refuse_other_agents_and_multistore(self):
        self.assertEqual(mod.summarize(report("main"), dry_run=True)["state"],
                         "unverified")
        mixed = {"stores": [{"agentId": "cron"}, {"agentId": "main"}]}
        self.assertEqual(mod.summarize(json.dumps(mixed).encode(), dry_run=False)["state"],
                         "unverified")

    def test_plan_calls_only_dry_run(self):
        invoked = []
        def fake_run(cmd, **kwargs):
            invoked.append(cmd)
            return SimpleNamespace(returncode=0, stdout=report(), stderr=b"")
        with patch.object(mod, "owned_file", return_value=True), \
             patch.object(mod.subprocess, "run", side_effect=fake_run):
            result, code = mod.execute(apply=False)
        self.assertEqual(code, 0)
        self.assertEqual(result["state"], "preview_only")
        self.assertEqual(len(invoked), 1)
        self.assertIn("--dry-run", invoked[0])
        self.assertNotIn("--enforce", invoked[0])
        self.assertEqual(invoked[0][invoked[0].index("--agent") + 1], "cron")

    def test_apply_requires_valid_preflight(self):
        invoked = []
        def fake_run(cmd, **kwargs):
            invoked.append(cmd)
            return SimpleNamespace(returncode=0, stdout=report("main"), stderr=b"")
        with patch.object(mod, "owned_file", return_value=True), \
             patch.object(mod.subprocess, "run", side_effect=fake_run):
            result, code = mod.execute(apply=True)
        self.assertEqual(code, 2)
        self.assertEqual(len(invoked), 1)
        self.assertEqual(result["state"], "preflight_unverified")

    def test_apply_invokes_native_gateway_after_plan(self):
        invoked = []
        def fake_run(cmd, **kwargs):
            invoked.append(cmd)
            return SimpleNamespace(returncode=0, stdout=report(), stderr=b"")
        with patch.object(mod, "owned_file", return_value=True), \
             patch.object(mod.subprocess, "run", side_effect=fake_run):
            result, code = mod.execute(apply=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["state"], "applied_by_native_maintenance")
        self.assertEqual(len(invoked), 2)
        self.assertIn("--dry-run", invoked[0])
        self.assertIn("--enforce", invoked[1])
        self.assertIn("--agent", invoked[1])
        self.assertEqual(invoked[1][invoked[1].index("--agent") + 1], "cron")
        self.assertNotIn("DO-NOT-LEAK", json.dumps(result))

    def test_unknown_output_refuses_apply(self):
        with patch.object(mod, "owned_file", return_value=True), \
             patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stdout=b"not-json", stderr=b"secret")) as call:
            result, code = mod.execute(apply=True)
        self.assertEqual(code, 2)
        self.assertEqual(call.call_count, 1)
        self.assertNotIn("secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
