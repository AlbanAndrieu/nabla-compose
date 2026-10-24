"""Offline tests for OpenClaw cron credential cutover; no native writes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / "scripts/workstation"
spec = importlib.util.spec_from_file_location("cron_cutover", BASE / "cutover-openclaw-cron-secret.py")
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)


def plan():
    return {
        "version": 1, "protocolVersion": 1,
        "generatedBy": "openclaw secrets configure",
        "targets": [{
            "type": "auth-profiles.api_key.key",
            "path": "profiles.litellm:default.key",
            "pathSegments": ["profiles", "litellm:default", "key"],
            "agentId": "cron",
            "ref": {"source": "env", "provider": "default",
                    "id": "LITELLM_OPENCLAW_CRON_API_KEY"},
        }],
    }


def result(files, mode="dry-run"):
    return {
        "mode": mode, "changed": True, "changedFiles": files,
        "refsChecked": 1, "warningCount": 0, "skippedExecRefs": 0,
        "checks": {"resolvability": True, "resolvabilityComplete": True},
    }


class CronCutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / ".local/share/nabla-compose"
        self.stage = self.root / "openclaw-import"
        self.stage.mkdir(parents=True, mode=0o700)
        self.state = self.home / ".openclaw"
        self.state.mkdir(mode=0o700)
        self.config = self.state / "openclaw.json"
        self.config.write_text('{"secrets":{"providers":{}}}')
        self.config.chmod(0o600)
        self.env = self.state / ".env"
        self.env.write_text("LITELLM_OPENCLAW_CRON_API_KEY=sk-SECRET_NEVER_PRINT\n")
        self.env.chmod(0o600)
        self.source = self.stage / "cron-plan.json"
        self.source.write_text(json.dumps(plan()))
        self.source.chmod(0o600)
        self.db = self.state / "agents/cron/agent/credentials.sqlite"
        self.db.parent.mkdir(parents=True, mode=0o700)
        self.key = self.root / "openclaw-cron.key"
        self.patches = [
            patch.object(cutover, "HOME", self.home),
            patch.object(cutover, "ROOT", self.root),
            patch.object(cutover, "STAGING", self.stage),
            patch.object(cutover, "SOURCE_PLAN", self.source),
            patch.object(cutover, "KEY_FILE", self.key),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_key_import_no_secret_echo(self):
        key = cutover.key_from_dotenv(self.env.read_bytes())
        self.assertEqual(key, b"sk-SECRET_NEVER_PRINT")
        with patch.object(cutover, "invoke", return_value=result(
                [str(self.db), str(self.env)])):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = cutover.main(["--check"])
        self.assertEqual(status, 0)
        self.assertIn("cron_cutover_key=would_create", output.getvalue())
        self.assertNotIn("sk-SECRET_NEVER_PRINT", output.getvalue())
        self.assertFalse(self.key.exists())

    def test_rejects_duplicate_indirect_and_short_keys(self):
        for value in (
            b"LITELLM_OPENCLAW_CRON_API_KEY=key\nLITELLM_OPENCLAW_CRON_API_KEY=otherkey\n",
            b"LITELLM_OPENCLAW_CRON_API_KEY=short\n",
            b"LITELLM_OPENCLAW_CRON_API_KEY=$" + b"{OTHER_KEY}\n",
        ):
            with self.subTest(value=value):
                with self.assertRaises(cutover.CutoverError):
                    cutover.key_from_dotenv(value)

    def test_builds_only_isolated_file_provider_and_disables_scrub(self):
        configured = cutover.plan_file(plan())
        self.assertEqual(configured["providerUpserts"], {
            "openclaw-cron": {"source": "file", "path": str(self.key),
                              "mode": "singleValue"}
        })
        self.assertEqual(configured["targets"][0]["ref"], {
            "source": "file", "provider": "openclaw-cron", "id": "value"
        })
        self.assertFalse(configured["options"]["scrubEnv"])
        self.assertEqual(plan()["targets"][0]["ref"]["source"], "env")

    def test_rejects_extraneous_files_and_unresolved_refs(self):
        with self.assertRaises(cutover.CutoverError):
            cutover.paths_checked(result([str(self.db), str(self.env)]),
                                  ["cron_auth_sqlite", "openclaw_config"])
        bad = result([str(self.db), str(self.config)])
        bad["checks"]["resolvabilityComplete"] = False
        with self.assertRaises(cutover.CutoverError):
            cutover.paths_checked(bad, ["cron_auth_sqlite", "openclaw_config"])

    def test_native_failure_never_displays_raw_cli_output(self):
        completed = CompletedProcess([], 1, b"sk-SECRET_NEVER_PRINT", b"SECRET_KEY")
        with patch.object(cutover.subprocess, "run", return_value=completed):
            with self.assertRaises(cutover.CutoverError):
                cutover.invoke(self.source)

    def test_check_blocks_unapproved_auth_profile(self):
        changed = plan()
        changed["targets"][0]["agentId"] = "main"
        self.source.write_text(json.dumps(changed))
        with patch.object(cutover.subprocess, "run") as native:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = cutover.main(["--check"])
        self.assertEqual(code, 2)
        native.assert_not_called()
        self.assertIn("cron_cutover_status=blocked", output.getvalue())
        self.assertFalse(self.key.exists())

    def test_check_never_writes_key_or_calls_real_apply(self):
        native_paths = result([str(self.db), str(self.env)])
        with patch.object(cutover, "invoke", return_value=native_paths) as call:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = cutover.main(["--check"])
        self.assertEqual(code, 0)
        call.assert_called_once_with(self.source)
        self.assertFalse(self.key.exists())
        self.assertFalse(list(self.stage.glob("cron-cutover-*")))
        self.assertIn("cron_cutover_applied=false", output.getvalue())


if __name__ == "__main__":
    unittest.main()
