"""Offline tests for safe embedding migration plan."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/workstation/plan-openclaw-memory-litellm.py"
spec = importlib.util.spec_from_file_location("memory_plan", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MemoryPlanTest(unittest.TestCase):
    def test_no_credentials_in_target(self):
        target, state = m.plan({"memory": {"search": {}}, "secrets": {"providers": {}}})
        self.assertEqual(state, "pending")
        self.assertEqual(target["remote"]["apiKey"],
                         {"source": "file", "provider": "openclaw-embeddings", "id": "value"})
        self.assertNotIn("sk-", str(target))
        self.assertEqual(target["fallback"], "none")

    def test_no_override_existing_provider(self):
        with self.assertRaises(ValueError):
            m.plan({"secrets": {"providers": {
                "openclaw-embeddings": {"source": "env", "id": "X"}
            }}})

    def test_invalid_config_fails_closed(self):
        with self.assertRaises(ValueError):
            m.plan({"memory": {"search": "invalid"}})


if __name__ == "__main__":
    unittest.main()
