"""Offline safeguards for scoped OpenClaw 429 cron route repair."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/repair-openclaw-429.py"
spec = importlib.util.spec_from_file_location("openclaw_429_repair", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    return {
        "models": {"providers": {
            "litellm-main": {
                "baseUrl": "http://172.17.0.57:4000/v1",
                "apiKey": "sk-MAIN-SYNTHETIC",
                "models": [{"id": "gpt-4.1"}],
            },
            "litellm-cron": {
                "baseUrl": "http://172.17.0.57:4000/v1",
                "apiKey": "sk-CRON-SYNTHETIC",
                "models": [{"id": "gpt-4.1"}],
            },
        }},
        "agents": {"defaults": {"model": {"primary": "litellm-main/gpt-4.1"},
                                "maxConcurrent": 4},
                   "list": [{"id": "main"}, {"id": "cron"}]},
        "memory": {"search": {"model": "embedding", "remote": {
            "apiKey": {"source": "file", "provider": "openclaw-embeddings", "id": "value"},
        }}},
        "channels": {"slack": {"enabled": True}},
    }


class RepairContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "openclaw.json"
        self.key = self.root / "openclaw-cron.key"
        self.config.write_text(json.dumps(sample()), encoding="utf-8")
        self.config.chmod(0o600)
        self.key.write_text("sk-CRON-SYNTHETIC\n", encoding="ascii")
        self.key.chmod(0o600)
        for attr, path in (("CONFIG", self.config), ("CRON_KEY", self.key)):
            patcher = patch.object(mod, attr, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_isolates_cron_and_preserves_main_memory_and_channels(self):
        original = sample()
        update = mod.candidate(original, "sk-CRON-SYNTHETIC", {"gpt-4.1"})
        self.assertEqual(update["agents"]["list"][1]["model"],
                         {"primary": "litellm-cron/gpt-4.1", "fallbacks": []})
        self.assertEqual(update["agents"]["defaults"]["maxConcurrent"], 1)
        self.assertEqual(update["agents"]["list"][0], original["agents"]["list"][0])
        self.assertEqual(update["memory"], original["memory"])
        self.assertEqual(update["channels"], original["channels"])
        self.assertEqual(original["agents"]["defaults"]["maxConcurrent"], 4)

    def test_does_not_change_default_gpt_provider(self):
        updated = mod.candidate(sample(), "sk-CRON-SYNTHETIC", {"gpt-4.1"})
        self.assertEqual(updated["agents"]["defaults"]["model"]["primary"],
                         "litellm-main/gpt-4.1")
        self.assertEqual(updated["models"], sample()["models"])

    def test_missing_authorization_blocks(self):
        with self.assertRaisesRegex(ValueError, "cron_model_not_authorized"):
            mod.candidate(sample(), "sk-CRON-SYNTHETIC", {"workstation-qwen"})

    def test_wrong_key_blocks(self):
        with self.assertRaisesRegex(ValueError, "cron_key_not_verified_distinct"):
            mod.candidate(sample(), "sk-INVALID-KEY", {"gpt-4.1"})

    def test_duplicate_agent_blocks(self):
        value = sample()
        value["agents"]["list"].append({"id": "cron"})
        with self.assertRaisesRegex(ValueError, "cron_agent_not_unique"):
            mod.candidate(value, "sk-CRON-SYNTHETIC", {"gpt-4.1"})

    def test_unexpected_existing_model_blocks(self):
        value = sample()
        value["agents"]["list"][1]["model"] = "some-other/model"
        with self.assertRaisesRegex(ValueError, "cron_model_unexpected"):
            mod.candidate(value, "sk-CRON-SYNTHETIC", {"gpt-4.1"})

    def test_inspection_does_not_write_or_restart(self):
        with patch.object(mod, "scoped_models", return_value={"gpt-4.1"}), \
             patch.object(mod, "apply_config") as apply, \
             patch.object(mod, "restart_gateway") as restart, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main([])
        self.assertEqual(result, 0)
        self.assertIn("configuration_changed=false", output.getvalue())
        apply.assert_not_called()
        restart.assert_not_called()

    def test_refuse_unreadable_key_without_sensitive_error(self):
        self.key.chmod(0o644)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main([])
        self.assertEqual(result, 2)
        self.assertIn("repair=blocked_private_config_or_key", output.getvalue())
        self.assertNotIn("sk-", output.getvalue())

    def test_atomic_apply_private_backup_and_no_restart(self):
        with patch.object(mod, "scoped_models", return_value={"gpt-4.1"}), \
             patch.object(Path, "home", return_value=self.root), \
             patch.object(mod, "restart_gateway") as restart, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--apply"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.config.read_text())["agents"]["list"][1]["model"]["primary"],
                         "litellm-cron/gpt-4.1")
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        backups = list((self.root / ".local/share/nabla-compose/openclaw-config-rollback").glob(
            "openclaw-before-cron-429-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), sample())
        self.assertNotIn("sk-CRON-SYNTHETIC", output.getvalue())
        restart.assert_not_called()

    def test_failed_restart_rolls_back_existing_config(self):
        with patch.object(mod, "scoped_models", return_value={"gpt-4.1"}), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "restart_gateway", side_effect=[False, True]), \
             patch.object(Path, "home", return_value=self.root), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--apply", "--restart-gateway"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(self.config.read_text()), sample())
        self.assertIn("gateway_restart=failed_rollback_attempted", output.getvalue())


if __name__ == "__main__":
    unittest.main()
