"""Coder key material: generated once, never printed, Gateway file kept in sync."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/ensure-openclaw-coder-key.py"
spec = importlib.util.spec_from_file_location("ensure_coder_key", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EnsureCoderKey(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.env = root / "litellm/.env.secrets"
        self.env.parent.mkdir()
        self.env.write_text("LITELLM_MASTER_KEY=sk-MASTER-SYNTHETIC\nLITELLM_OPENCLAW_MAIN_API_KEY=sk-MAIN-SYNTHETIC")
        self.env.chmod(0o600)
        self.key = root / "state/credentials/litellm/coder.key"
        self.ids = dict(uid=os.getuid(), gid=os.getgid())

    def run_script(self, apply):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.run(apply, self.env, self.key, **self.ids)
        return code, output.getvalue()

    def test_plan_changes_nothing(self):
        before = self.env.read_text()
        code, output = self.run_script(False)
        self.assertEqual(code, 0)
        self.assertIn("litellm_runtime_key=missing", output)
        self.assertEqual(self.env.read_text(), before)
        self.assertFalse(self.key.exists())

    def test_apply_generates_once_keeps_other_lines_and_syncs_gateway(self):
        code, output = self.run_script(True)
        self.assertEqual(code, 0)
        value = module.env_value(self.env)
        self.assertTrue(value.startswith("sk-") and len(value) > 40)
        self.assertNotIn(value, output)
        content = self.env.read_text()
        self.assertTrue(content.startswith("LITELLM_MASTER_KEY=sk-MASTER-SYNTHETIC\nLITELLM_OPENCLAW_MAIN_API_KEY="))
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        backups = list(self.env.parent.glob(".env.secrets.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.key.read_text(), value + "\n")
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.key.parent.stat().st_mode & 0o777, 0o700)

        code, output = self.run_script(True)
        self.assertEqual(code, 0)
        self.assertEqual(module.env_value(self.env), value)
        self.assertIn("gateway_key_file=in_sync", output)
        self.assertEqual(len(list(self.env.parent.glob(".env.secrets.bak-*"))), 1)

    def test_existing_value_is_never_rotated_and_drifted_gateway_file_is_rewritten(self):
        self.env.write_text(self.env.read_text() + "\nLITELLM_OPENCLAW_CODER_API_KEY=\"sk-CODER-SYNTHETIC\"\n")
        self.key.parent.mkdir(parents=True)
        self.key.write_text("sk-STALE\n")
        code, output = self.run_script(True)
        self.assertEqual(code, 0)
        self.assertIn("litellm_runtime_key=present", output)
        self.assertIn("gateway_key_file=differs", output)
        self.assertEqual(self.key.read_text(), "sk-CODER-SYNTHETIC\n")
        self.assertNotIn("SYNTHETIC", output)

    def test_missing_runtime_file_fails_closed(self):
        self.env.unlink()
        code, output = self.run_script(True)
        self.assertEqual(code, 2)
        self.assertIn("litellm_runtime_file=missing", output)


if __name__ == "__main__":
    unittest.main()
