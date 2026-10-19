"""Offline TrueNAS native Cron job registration contract."""

from __future__ import annotations

import contextlib
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from unittest import TestCase, main, mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/reconcile-defectdojo-artifact-cron.py"
SPEC = importlib.util.spec_from_file_location("defectdojo_cron", SOURCE)
assert SPEC and SPEC.loader
cron = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cron)


class NativeCronContract(TestCase):
    def test_cron_is_disabled_and_not_an_importer(self):
        self.assertFalse(cron.JOB["enabled"])
        self.assertIn("--pull", cron.JOB["command"])
        self.assertNotIn("--pull-and-import", cron.JOB["command"])
        self.assertEqual(cron.JOB["user"], "root")
        self.assertEqual(cron.JOB["schedule"]["minute"], "50")
        self.assertEqual(cron.JOB["schedule"]["hour"], "06")

    def test_check_has_no_midclt_call(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--check"]),
            mock.patch.object(cron, "middleware", side_effect=AssertionError("live access")),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)

    def test_apply_creates_only_disabled_job(self):
        calls = []
        with (
            mock.patch.object(sys, "argv", ["cron", "--apply"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value=None),
            mock.patch.object(cron, "middleware", side_effect=lambda *v: calls.append(v)),
            contextlib.redirect_stdout(StringIO()),
        ):
            self.assertEqual(cron.main(), 0)
        self.assertEqual(calls[0][0], "cronjob.create")
        self.assertFalse(calls[0][1]["enabled"])

    def test_enable_requires_explicit_approval(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--enable"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value={**cron.JOB, "id": 1}),
            mock.patch.object(cron.os, "environ", {}),
            mock.patch.object(cron, "middleware") as mutation,
        ):
            with self.assertRaises(RuntimeError):
                cron.main()
        mutation.assert_not_called()

    def test_app_credentials_gate_enable(self):
        with (
            mock.patch.object(sys, "argv", ["cron", "--enable"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value={**cron.JOB, "id": 1}),
            mock.patch.object(cron.os, "environ", {"DEFECTDOJO_GH_POLL_APPROVED": "YES"}),
            mock.patch.object(cron, "require_app_material", side_effect=RuntimeError("missing key")),
            mock.patch.object(cron, "middleware") as mutation,
        ):
            with self.assertRaises(RuntimeError):
                cron.main()
        mutation.assert_not_called()

    def test_refuse_ownership_drift(self):
        drift = {**cron.JOB, "id": 9, "command": "unrelated"}
        with (
            mock.patch.object(sys, "argv", ["cron", "--apply"]),
            mock.patch.object(cron, "require_environment"),
            mock.patch.object(cron, "existing_job", return_value=drift),
        ):
            with self.assertRaises(RuntimeError):
                cron.main()


if __name__ == "__main__":
    main()
