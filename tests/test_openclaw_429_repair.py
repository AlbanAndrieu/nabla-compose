"""Offline safeguards for scoped OpenClaw 429 cron route repair."""
import contextlib
import hashlib
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

    def test_default_agent_without_list_is_valid_concurrency_only(self):
        original = sample()
        del original["agents"]["list"]
        update = mod.candidate(original, "sk-CRON-SYNTHETIC", {"gpt-4.1"})
        self.assertEqual(mod.repair_scope(original), "concurrency_only")
        self.assertEqual(update["agents"]["defaults"]["maxConcurrent"], 1)
        self.assertNotIn("list", update["agents"])
        self.assertEqual(update["models"], original["models"])
        self.assertEqual(update["memory"], original["memory"])

    def test_empty_agent_list_does_not_invent_cron_agent(self):
        original = sample()
        original["agents"]["list"] = []
        update = mod.candidate(original, "sk-CRON-SYNTHETIC", {"gpt-4.1"})
        self.assertEqual(update["agents"]["list"], [])
        self.assertEqual(mod.repair_scope(original), "concurrency_only")

    def test_implicit_agent_does_not_access_cron_credentials_or_models(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        self.key.unlink()
        with patch.object(mod, "scoped_models") as model_probe, \
             patch.object(mod, "native_patch_concurrency", return_value="applied") as rpc, \
             patch.object(mod, "apply_config") as direct, \
             patch.object(mod, "service_active", return_value=True), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--apply", "--restart-gateway"])
        self.assertEqual(result, 0)
        model_probe.assert_not_called()
        direct.assert_not_called()
        rpc.assert_called_once()
        self.assertIn("cron_key_access=not_required", output.getvalue())
        self.assertIn("cron_route_change=not_applicable_no_named_agent", output.getvalue())

    def test_default_agent_apply_uses_rpc_not_direct_overwrite(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        with patch.object(mod, "scoped_models", return_value={"gpt-4.1"}), \
             patch.object(mod, "service_active", return_value=True), \
             patch.object(mod, "native_patch_concurrency", return_value="applied") as rpc, \
             patch.object(mod, "apply_config") as direct, \
             patch.object(mod, "restart_gateway") as restart, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = mod.main(["--apply", "--restart-gateway"])
        self.assertEqual(result, 0)
        rpc.assert_called_once()
        direct.assert_not_called()
        restart.assert_not_called()
        self.assertIn("repair_scope=concurrency_only", output.getvalue())
        self.assertIn("cron_route_change=not_applicable_no_named_agent", output.getvalue())
        self.assertIn("native_config_patch=applied", output.getvalue())

    def test_native_rpc_optimistic_hash_and_private_backup(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        def rpc(method, params):
            if method == "config.get":
                return {"hash": hashlib.sha256(self.config.read_bytes()).hexdigest()}
            self.assertEqual(method, "config.patch")
            self.assertEqual(params["baseHash"], hashlib.sha256(self.config.read_bytes()).hexdigest())
            patch_value = json.loads(params["raw"])
            self.assertEqual(set(patch_value), {"agents"})
            self.assertEqual(set(patch_value["agents"]), {"defaults"})
            self.assertEqual(set(patch_value["agents"]["defaults"]), {"maxConcurrent"})
            new = json.loads(self.config.read_text())
            new["agents"]["defaults"]["maxConcurrent"] = patch_value["agents"]["defaults"]["maxConcurrent"]
            self.config.write_text(json.dumps(new))
            self.config.chmod(0o600)
            return {"ok": True}
        with patch.object(mod, "gateway_call", side_effect=rpc), \
             patch.object(Path, "home", return_value=self.root):
            result = mod.native_patch_concurrency(original, self.config.read_bytes())
        self.assertEqual(result, "applied")
        self.assertEqual(json.loads(self.config.read_text())["agents"]["defaults"]["maxConcurrent"], 1)
        backups = list((self.root / ".local/share/nabla-compose/openclaw-config-rollback").glob(
            "openclaw-before-native-429-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_native_rpc_rejects_mismatched_snapshot_without_write(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        with patch.object(mod, "gateway_snapshot_hash", return_value="a" * 64), \
             patch.object(mod, "gateway_call") as rpc, \
             patch.object(Path, "home", return_value=self.root):
            result = mod.native_patch_concurrency(original, self.config.read_bytes())
        self.assertEqual(result, "blocked_gateway_snapshot")
        rpc.assert_not_called()
        self.assertEqual(json.loads(self.config.read_text()), original)

    def test_native_rpc_refusal_does_not_fallback_to_direct_write(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        with patch.object(mod, "gateway_snapshot_hash",
                          return_value=hashlib.sha256(self.config.read_bytes()).hexdigest()), \
             patch.object(mod, "gateway_call", return_value=None), \
             patch.object(Path, "home", return_value=self.root):
            result = mod.native_patch_concurrency(original, self.config.read_bytes())
        self.assertEqual(result, "blocked_native_patch")
        self.assertEqual(json.loads(self.config.read_text()), original)

    def test_native_patch_rolls_back_if_gateway_response_is_lost(self):
        original = sample()
        del original["agents"]["list"]
        self.config.write_text(json.dumps(original))
        count = [0]
        def mock_rpc(method, params):
            if method == "config.get":
                return {"hash": hashlib.sha256(self.config.read_bytes()).hexdigest()}
            self.assertEqual(method, "config.patch")
            count[0] += 1
            new_value = json.loads(params["raw"])["agents"]["defaults"]["maxConcurrent"]
            value = json.loads(self.config.read_text())
            value["agents"]["defaults"]["maxConcurrent"] = new_value
            self.config.write_text(json.dumps(value))
            self.config.chmod(0o600)
            # Simulate a lost success response after an otherwise committed patch.
            return None if count[0] == 1 else {"ok": True}
        with patch.object(mod, "gateway_call", side_effect=mock_rpc), \
             patch.object(Path, "home", return_value=self.root):
            result = mod.native_patch_concurrency(original, self.config.read_bytes())
        self.assertEqual(result, "failed_rollback_verified")
        self.assertEqual(json.loads(self.config.read_text()), original)
        self.assertEqual(count[0], 2)

    def test_missing_defaults_map_is_created_without_agent(self):
        original = sample()
        del original["agents"]["list"]
        del original["agents"]["defaults"]
        updated = mod.candidate(original, "sk-CRON-SYNTHETIC", {"gpt-4.1"})
        self.assertEqual(updated["agents"]["defaults"]["maxConcurrent"], 1)
        self.assertNotIn("list", updated["agents"])

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

    def test_config_target_is_resolved_at_call_time(self):
        # Regression: path=CONFIG in a function signature freezes the real
        # ~/.openclaw path before the temporary test fixture is installed.
        # That previously made the apply and rollback tests return blocked_write.
        self.assertEqual(mod.apply_config.__defaults__, (None,))
        self.assertNotEqual(self.config, Path.home() / ".openclaw/openclaw.json")

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
