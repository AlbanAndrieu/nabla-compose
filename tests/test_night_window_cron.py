"""Offline contract for the night-window TrueNAS cron jobs."""

from __future__ import annotations

import contextlib
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from unittest import TestCase, main, mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/reconcile-night-window-cron.py"
SPEC = importlib.util.spec_from_file_location("night_window_cron", SOURCE)
assert SPEC and SPEC.loader
cron = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cron)


class NightWindowCron(TestCase):
    def test_start_skips_sunday_and_stop_runs_daily(self):
        start, stop = cron.JOBS
        self.assertEqual((start["schedule"]["hour"], start["schedule"]["dow"]), ("01", "1-6"))
        self.assertTrue(start["command"].endswith("restore-optional-apps.sh --start"))
        self.assertEqual((stop["schedule"]["hour"], stop["schedule"]["dow"]), ("07", "*"))
        self.assertTrue(stop["command"].endswith("restore-optional-apps.sh --stop"))
        self.assertIn("night-window-apps.txt", start["command"])

    def test_listed_apps_are_never_started_by_day(self):
        lines = (ROOT / "config/truenas/night-window-apps.txt").read_text(encoding="utf-8").splitlines()
        apps = [line for line in lines if line and not line.startswith("#")]
        self.assertIn("bitcoind", apps)
        self.assertEqual(apps, sorted(set(apps)))
        # Probed 24/7 (n8n is called by OpenClaw) or kept stopped by the operator.
        self.assertFalse({"n8n", "scrutiny", "graylog", "kasm-workspaces", "homarr"} & set(apps))
        manifest = yaml.safe_load((ROOT / "config/truenas/custom-apps.yml").read_text(encoding="utf-8"))
        for entry in manifest["apps"]:
            if entry["name"] in apps:
                self.assertEqual(entry.get("state"), "stopped", entry["name"])

    def test_check_is_offline(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--check"]),
            mock.patch.object(cron, "middleware", side_effect=AssertionError("live access")),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)

    def test_apply_creates_missing_and_refuses_drift(self):
        calls = []
        existing = [{**cron.JOBS[1], "id": 7}]
        with (
            mock.patch.object(sys, "argv", ["cron", "--apply"]),
            mock.patch.object(cron.os, "geteuid", return_value=0),
            mock.patch.object(cron, "APPS_FILE", ROOT / "config/truenas/night-window-apps.txt"),
            mock.patch.object(cron, "CHECKOUT", ROOT),
            mock.patch.object(cron, "middleware",
                              side_effect=lambda *v: existing if v[0] == "cronjob.query" else calls.append(v)),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)
        self.assertEqual([(c[0], c[1]["description"]) for c in calls],
                         [("cronjob.create", "nabla-night-window-start")])
        drifted = [{**cron.JOBS[0], "schedule": {**cron.JOBS[0]["schedule"], "hour": "02"}}]
        with (
            mock.patch.object(sys, "argv", ["cron", "--apply"]),
            mock.patch.object(cron.os, "geteuid", return_value=0),
            mock.patch.object(cron, "APPS_FILE", ROOT / "config/truenas/night-window-apps.txt"),
            mock.patch.object(cron, "CHECKOUT", ROOT),
            mock.patch.object(cron, "middleware", return_value=drifted),
        ):
            with self.assertRaises(RuntimeError):
                cron.main()


if __name__ == "__main__":
    main()
