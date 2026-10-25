"""Offline scoped AI recovery contracts; never call TrueNAS or read real secrets."""
from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-ai-secret-recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ai_secret_scope", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AiSecretRecoveryScopeTest(unittest.TestCase):
    def test_openrag_scope_ignores_scrutiny_and_litellm(self):
        mod = load_module()
        checked_secrets, checked_apps, checked_containers = [], [], []

        def fake_secret(path, required):
            checked_secrets.append(str(path))
            return {"ready": True, "issues": [], "missingKeys": []}

        def fake_app(name):
            checked_apps.append(name)
            return {"state": "RUNNING", "legacyScrutinyEnvFile": "unknown"}

        def fake_container(name):
            checked_containers.append(name)
            return {"status": "running", "health": "healthy"}

        with patch.object(mod, "check_secret", side_effect=fake_secret), \
             patch.object(mod, "query_app", side_effect=fake_app), \
             patch.object(mod, "inspect_container", side_effect=fake_container):
            result = mod.assess("openrag")

        self.assertEqual(result["scope"], "openrag")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(list(result["secrets"]), ["openrag"])
        self.assertNotIn("scrutiny", checked_apps)
        self.assertNotIn("litellm", checked_apps)
        self.assertNotIn("scrutiny", " ".join(checked_containers))
        self.assertEqual(
            checked_secrets,
            ["/mnt/cpool/secrets/runtime/openrag/.env.secrets"],
        )

    def test_scoped_secret_incomplete_blocks_openrag(self):
        mod = load_module()
        with patch.object(
            mod, "check_secret",
            return_value={"ready": False, "issues": ["required keys missing"]},
        ), patch.object(
            mod, "query_app",
            return_value={"state": "RUNNING", "legacyScrutinyEnvFile": "unknown"},
        ), patch.object(
            mod, "inspect_container", return_value={"health": "healthy"},
        ):
            report = mod.assess("openrag")
        self.assertEqual(len(report["blockers"]), 1)
        self.assertTrue(report["blockers"][0].startswith("openrag:"))
        self.assertFalse(any("scrutiny" in x for x in report["blockers"]))

    def test_scope_is_declared_in_runner_and_rejects_unknown(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "--scope", "unknown"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        source = SCRIPT.read_text(encoding="utf-8")
        registry = (ROOT / "scripts/truenas/migration-diagnostic-sections.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--scope openrag", registry)
        self.assertIn('choices=tuple(SCOPES)', source)
        self.assertIn('"openrag": BASE / "secrets/runtime/openrag/.env.secrets"', source)

    def test_checks_never_call_mutating_app_actions(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("app.redeploy", "app.start", "docker start", "docker compose up"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
