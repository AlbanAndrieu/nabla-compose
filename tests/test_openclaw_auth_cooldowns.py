"""Offline contracts: OpenClaw 429 auth cooldown metadata is redacted."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/diagnose-openclaw-auth-cooldowns.py"
spec = importlib.util.spec_from_file_location("openclaw_cooldown", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CooldownContracts(unittest.TestCase):
    def test_counts_rate_and_billing_without_identity_leaks(self):
        payload = b'{"auth":{"unusableProfiles":[{"id":"sk-PRIVATE-KEY","reason":"rate_limit"},{"id":"user@example.net","reason":"billing_disabled"},{"reason":"other"}]}}'
        with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=payload, stderr=b"PRIVATE-STDERR")) as runner, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main([])
        self.assertEqual(code, 0)
        self.assertEqual(runner.call_args.args[0],
                         ["openclaw", "models", "status", "--json"])
        self.assertIn("openclaw_unusable_rate_cooldown_count=1", output.getvalue())
        self.assertIn("openclaw_unusable_billing_count=1", output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertNotIn("example.net", output.getvalue())

    def test_dict_schema_is_supported(self):
        counts = module.summarize({"auth":{"unusableProfiles":{
            "provider1": [{"reason": "429"}],
            "provider2": {"reason": "cooldown"},
        }}})
        self.assertEqual(counts["rate_cooldown"], 2)

    def test_unrecognized_schema_fails_closed(self):
        with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b'{"auth":{}}', stderr=b"private")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main([])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized_schema", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_command_failure_suppresses_private_output(self):
        with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                returncode=2, stdout=b"secret", stderr=b"sk-SECRET")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.main([])
        self.assertEqual(code, 2)
        self.assertNotIn("secret", output.getvalue().lower())
        self.assertIn("unavailable", output.getvalue())

if __name__ == "__main__":
    unittest.main()
