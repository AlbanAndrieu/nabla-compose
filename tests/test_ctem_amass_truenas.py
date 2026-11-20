"""Offline CTEM TrueNAS job and Cron contract tests (no Docker or middleware)."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CRON = ROOT / "scripts/truenas/reconcile-ctem-amass-cron.py"
RUNNER = ROOT / "scripts/security/run-ctem-amass-truenas.sh"
COMPOSE = ROOT / "config/security/ctem/amass-job.compose.yml"
MODULE = runpy.run_path(str(CRON))


class AmassTrueNASContractTests(unittest.TestCase):
    def test_manual_compose_has_no_host_ports_or_privileged_mounts(self):
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("profiles:", source)
        self.assertIn("manual", source)
        self.assertIn("network_mode: bridge", source)
        self.assertIn("read_only: true", source)
        self.assertIn("no-new-privileges:true", source)
        self.assertIn("cap_drop:", source)
        self.assertIn("restart: \"no\"", source)
        self.assertNotIn("ports:", source)
        self.assertNotIn("network_mode: host", source)
        self.assertNotIn("/var/run/docker.sock", source)
        self.assertNotIn("privileged: true", source)

    def test_cron_is_disabled_by_default_and_weekly(self):
        job = MODULE["JOB"]
        self.assertFalse(job["enabled"])
        self.assertEqual(job["user"], "root")
        self.assertEqual(job["schedule"]["dow"], "0")
        self.assertIn("run-ctem-amass-truenas.sh --run", job["command"])
        self.assertNotIn("docker ", job["command"])

    def test_cron_detects_existing_contract_drift(self):
        same = MODULE["same_contract"]
        spec = MODULE["JOB"].copy()
        self.assertTrue(same(spec))
        self.assertFalse(same({**spec, "command": "curl -k http://localhost"}))
        self.assertFalse(same({**spec, "schedule": {"minute": "0"}}))

    def test_check_is_offline_no_middleware(self):
        main = MODULE["main"]
        with patch.object(sys, "argv", [str(CRON), "--check"]):
            with patch.dict(main.__globals__, {"middleware":
                            lambda *args: self.fail("middleware called")}):
                self.assertEqual(main(), 0)

    def test_enable_requires_approval_and_installed_binary(self):
        main = MODULE["main"]
        original = main.__globals__
        previous = {**MODULE["JOB"], "id": 7, "enabled": False}
        with patch.object(sys, "argv", [str(CRON), "--enable"]):
            with patch.dict(original, {
                "require_root_checkout": lambda: None,
                "existing_job": lambda: previous,
                "require_execution_ready": lambda: self.fail("should reject before probing"),
                "middleware": lambda *args: self.fail("should not mutate"),
            }):
                with patch.dict("os.environ", {"CTEM_AMASS_CRON_APPROVED": ""}):
                    with self.assertRaisesRegex(RuntimeError, "APPROVED"):
                        main()

    def test_runner_has_lock_and_private_export(self):
        source = RUNNER.read_text(encoding="utf-8")
        for expected in ("flock -n", "umask 077", "--no-deps", "--pull never",
                         "--private-output", "stat -c '%u:%a'", "--check"):
            self.assertIn(expected, source)
        self.assertNotIn("--active", source)
        self.assertNotIn("git pull", source)
        self.assertNotIn("docker compose up", source)


if __name__ == "__main__":
    unittest.main()
