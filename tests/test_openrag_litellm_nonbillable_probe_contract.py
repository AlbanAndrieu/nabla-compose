"""Offline regression contracts: OpenRAG preflight must not request protected models anonymously."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-openrag-startup.sh"


class OpenRagLiteLLMProbeContract(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text(encoding="utf-8")

    def test_workstation_proxy_uses_anonymous_liveliness(self):
        self.assertIn("http://172.17.0.57:4000/health/liveliness", self.text)
        self.assertIn("litellm_liveliness=HTTP_200 models_auth=not_tested", self.text)

    def test_no_active_anonymous_model_list_or_inference_probe(self):
        active = "\n".join(line for line in self.text.splitlines()
                           if not line.lstrip().startswith("#"))
        self.assertNotIn("/v1/models", active)
        self.assertNotIn("/v1/chat/completions", active)
        self.assertNotIn("/v1/embeddings", active)
        self.assertNotIn("/health\'", active)

    def test_contract_protects_secrets_and_preserves_lifecycle_gate(self):
        self.assertIn("OPENRAG_STARTUP_PREFLIGHT=BLOCKED", self.text)
        self.assertIn("No key or model request.", self.text)
        self.assertRegex(self.text, r"litellm_status=\\\"\\$\\(http_code")
        self.assertNotIn("Authorization: Bearer", self.text)

if __name__ == "__main__":
    unittest.main()
