"""Synthetic tests: OpenClaw embedding cutover does not expose or overwrite secrets."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import json

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

    def test_schema_draft_selected_from_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed in local test environment")
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "memory": {
                    "type": "object",
                    "properties": {"search": {
                        "type": "object",
                        "properties": {
                            "provider": {"enum": ["openai-compatible"]},
                            "model": {"type": "string"},
                            "remote": {"type": "object", "properties": {
                                "apiKey": {"anyOf": [{"type": "string"}, {
                                    "type": "object", "properties": {
                                        "source": {"const": "file"}
                                    }
                                }]}
                            }},
                            "fallback": {"type": "string"},
                            "enabled": {"type": "boolean"}
                        }
                    }}
                },
                "secrets": {"type": "object", "properties": {
                    "providers": {"type": "object"}
                }}
            }
        }
        from subprocess import CompletedProcess
        proc = CompletedProcess(["openclaw"], 0, stdout=json.dumps(schema).encode())
        with patch.object(module.subprocess, "run", return_value=proc):
            module.verify_schema({"memory": {"search": {
                "provider": "openai-compatible", "model": "embedding",
                "remote": {"apiKey": {"source": "file"}}, "fallback": "none",
                "enabled": True}}, "secrets": {"providers": {}}})
            with self.assertRaises(jsonschema.exceptions.ValidationError):
                module.verify_schema({"memory": {"search": {"provider": "invalid"}},
                                      "secrets": {"providers": {}}})

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
