"""Offline contracts for the TrueNAS generic LiteLLM catalogue.

No runtime access, secret material, model inference or third-party services.
"""
import re
import unittest
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "apps/litellm/config.yaml"
SOURCE = CONFIG.read_text(encoding="utf-8")


def active_models():
    parts = re.split(r"(?m)^  - model_name: ", SOURCE)
    for part in parts[1:]:
        name, _, body = part.partition("\n")
        yield name.split("#", 1)[0].strip(), body.split("\nmcp_servers:", 1)[0]


class TrueNASGenericLiteLLMTests(unittest.TestCase):
    def test_forbidden_private_deployment_material_is_absent(self):
        # Exclusion applies to aliases, comments, endpoints and secret names.
        fragments = ("jm-", "jm_", "jusai", "jusmundi", "jm-dataai")
        for forbidden in fragments:
            self.assertNotIn(forbidden, SOURCE.lower())

    def test_generic_models_align_with_gpu_workstation(self):
        routes = dict(active_models())
        generic = ("llama3.2", "llama3.1", "llama3.8b",
                   "deepseek-coder-v2", "qwen", "gemma3", "rr-json")
        for name in generic:
            with self.subTest(model=name):
                self.assertIn(name, routes)
                self.assertIn("172.17.0.57:11434", routes[name])
        self.assertEqual(len(routes), len(set(routes)))

    def test_critical_existing_routes_are_preserved(self):
        routes = dict(active_models())
        self.assertIn("embedding", routes)
        self.assertIn("model: openai/embedding", routes["embedding"])
        self.assertIn("LITELLM_WORKSTATION_API_BASE", routes["embedding"])
        self.assertIn("embedding-local", routes)
        self.assertIn("172.17.0.24:30068", routes["embedding-local"])
        for alias in ("workstation-qwen", "fastapi-qwen",
                      "hermes-opus-5-5", "hermes-opus-5",
                      "hermes-opus-4-8", "hermes-openai"):
            self.assertIn(alias, routes)

    def test_no_unsupported_fallbacks_or_retry_amplification(self):
        models = {name for name, _ in active_models()}
        section = SOURCE.split("\nlitellm_settings:", 1)[1].split(
            "\nrouter_settings:", 1)[0]
        fallback = section.split("  fallbacks:", 1)[1].split(
            "  default_fallbacks:", 1)[0]
        refs = re.findall(r'"([A-Za-z0-9_.-]+)"', fallback)
        for name in refs:
            self.assertIn(name, models)
        self.assertIn("num_retries: 1", section)
        self.assertIn("routing_strategy: least-busy", SOURCE)
        self.assertIn("enable_pre_call_checks: true", SOURCE)
        self.assertNotIn("num_retries: 5", SOURCE)

    def test_optional_paid_generic_providers_not_active(self):
        routes = dict(active_models())
        for alias in ("gpt-image", "claude-3-5-sonnet-20241022", "deepseek-chat"):
            self.assertNotIn(alias, routes)


if __name__ == "__main__":
    unittest.main()
