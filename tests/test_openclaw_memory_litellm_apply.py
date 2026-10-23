"""Synthetic tests: OpenClaw embedding cutover does not expose or overwrite secrets."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "scripts/workstation/apply-openclaw-memory-litellm.py"
spec = importlib.util.spec_from_file_location("apply_memory", p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CutoverTest(unittest.TestCase):
    def test_preserves_other_credentials_and_settings(self):
        cfg = {
            "models": {"providers": {"litellm-main": {"apiKey": "DO_NOT_TOUCH"}}},
            "memory": {"search": {"sources": ["memory"], "cache": {"enabled": True}}},
            "secrets": {"providers": {}},
        }
        updated, state = module.candidate(cfg)
        self.assertEqual(state, "pending")
        self.assertEqual(updated["models"], cfg["models"])
        self.assertEqual(updated["memory"]["search"]["sources"], ["memory"])
        self.assertEqual(updated["memory"]["search"]["cache"], {"enabled": True})
        self.assertEqual(updated["memory"]["search"]["remote"]["apiKey"]["source"], "file")
        self.assertNotIn("openclaw-embeddings", cfg["secrets"]["providers"])

    def test_fails_closed_when_existing_provider_differs(self):
        with self.assertRaises(ValueError):
            module.candidate({"memory": {"search": {"provider": "openai"}}})

    def test_idempotent_candidate(self):
        original = {"memory": {"search": {}}, "secrets": {"providers": {}}}
        first, state = module.candidate(original)
        second, state2 = module.candidate(first)
        self.assertEqual(state, "pending")
        self.assertEqual(state2, "already_configured")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
