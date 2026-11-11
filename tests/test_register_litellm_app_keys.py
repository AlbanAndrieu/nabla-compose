"""Offline contract for per-application LiteLLM virtual key registration."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/register-litellm-app-keys.py"
spec = importlib.util.spec_from_file_location("register_litellm_app_keys", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VALUE = "sk-app-value-never-printed"


class RegisterAppKeysTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        runtime = Path(temp.name) / ".env.secrets"
        runtime.write_text(f"OTHER=x\nHOMARR_ASSISTANT_API_KEY='{VALUE}'\n", encoding="utf-8")
        config = Path(temp.name) / "app-keys.json"
        config.write_text(json.dumps({"version": 1, "keys": [{
            "alias": "homarr-assistant", "runtimeFile": str(runtime),
            "variable": "HOMARR_ASSISTANT_API_KEY", "models": ["qwen"],
            "maxBudgetUsd": 1, "budgetDuration": "30d"}]}), encoding="utf-8")
        for target, value in ((module, ("CONFIG", config)),
                              (module.lib, ("container_environment",
                                            lambda: {"LITELLM_MASTER_KEY": "sk-master"}))):
            patcher = patch.object(target, *value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, responses, *argv):
        with patch.object(module.lib, "request", side_effect=responses) as request, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main(list(argv))
        self.assertNotIn(VALUE, output.getvalue())
        return code, output.getvalue(), request

    def test_plan_never_registers(self):
        code, output, request = self.run_main([(404, None)])
        self.assertEqual(code, 0)
        self.assertIn("homarr_assistant_registration=planned", output)
        self.assertEqual(request.call_count, 1)

    def test_apply_registers_only_a_missing_key(self):
        code, output, request = self.run_main([(404, None), (200, {})], "--apply")
        self.assertEqual(code, 0)
        path, master, body = request.call_args_list[1].args
        self.assertEqual((path, master), ("/key/generate", "sk-master"))
        self.assertEqual(body["key"], VALUE)
        self.assertEqual(body["models"], ["qwen"])
        self.assertEqual(body["max_budget"], 1)

    def test_existing_key_is_never_regenerated(self):
        code, output, request = self.run_main([(200, {"info": {"models": ["qwen"]}})], "--apply")
        self.assertEqual(code, 0)
        self.assertIn("homarr_assistant_model_scope=verified", output)
        self.assertEqual(request.call_count, 1)

    def test_unverified_presence_fails_closed(self):
        code, output, _ = self.run_main([(500, None)], "--apply")
        self.assertEqual(code, 2)
        self.assertIn("homarr_assistant_presence=unverified", output)

    def test_committed_keys_are_scoped_and_budgeted(self):
        keys = json.loads((ROOT / "config/litellm/app-keys.json").read_text())["keys"]
        for key in keys:
            self.assertTrue(key["models"])
            self.assertGreater(key["maxBudgetUsd"], 0)
            self.assertTrue(key["runtimeFile"].startswith("/mnt/cpool/secrets/runtime/"))


if __name__ == "__main__":
    unittest.main()
