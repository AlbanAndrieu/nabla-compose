"""Standard-library contracts: provider audit never prints URLs or credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-route-metadata.py"


class OpenClawRouteMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "openclaw.json"

    def inspect(self, config):
        self.config.write_text(json.dumps(config), encoding="utf-8")
        env = dict(os.environ, OPENCLAW_CONFIG_PATH=str(self.config), OPENCLAW_STATE_DIR=str(self.tmp.name))
        return subprocess.run(
            [sys.executable, str(SCRIPT)], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=10,
        )

    def test_redacts_endpoint_and_api_key(self):
        secret = "private-credential-test-marker"
        hostname = "private-host-test.invalid"
        result = self.inspect({
            "models": {"providers": {"litellm-main": {
                "baseUrl": "https://name:password@" + hostname + ":4000/v1",
                "apiKey": secret,
            }}},
            "agents": {"defaults": {"memorySearch": {"provider": "openai"}}},
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("provider=litellm-main", result.stdout)
        self.assertIn("credential_in_url=yes", result.stdout)
        self.assertIn("memory_provider=present", result.stdout)
        self.assertIn("route_owner=other_or_unverified", result.stdout)
        self.assertIn("key_representation=literal_or_unresolved", result.stdout)
        for private in (secret, hostname, "password"):
            self.assertNotIn(private, result.stdout + result.stderr)

    def test_truenas_and_local_provider_routes_are_classified(self):
        result = self.inspect({
            "models": {"providers": {
                "litellm-main": {
                    "baseUrl": "http://172.17.0.24:4000/v1",
                    "apiKey": {"source": "file", "provider": "openclaw-main", "id": "value"},
                },
                "litellm-cron": {
                    "baseUrl": "http://127.0.0.1:4000/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
            }}
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("route_owner=truenas_litellm", result.stdout)
        self.assertIn("route_owner=workstation_litellm", result.stdout)
        self.assertIn("key_representation=secretref_object", result.stdout)
        self.assertNotIn("sk-SHOULD_NOT_PRINT", result.stdout)
        self.assertNotIn("openclaw-main", result.stdout)

    def test_workstation_lan_and_malformed_port_are_safe(self):
        result = self.inspect({
            "models": {"providers": {
                "litellm-main": {
                    "baseUrl": "http://172.17.0.57:4000/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
                "litellm-cron": {
                    "baseUrl": "http://private-host.invalid:secret-port/v1",
                    "apiKey": "sk-SHOULD_NOT_PRINT",
                },
            }}
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("route_owner=workstation_lan_litellm", result.stdout)
        self.assertIn("route_owner=other_or_unverified", result.stdout)
        self.assertNotIn("private-host.invalid", result.stdout + result.stderr)
        self.assertNotIn("secret-port", result.stdout + result.stderr)
        self.assertNotIn("sk-SHOULD_NOT_PRINT", result.stdout + result.stderr)

    def test_missing_base_url_is_classified_without_unbound_variable(self):
        result = self.inspect({"models": {"providers": {"litellm-main": {"apiKey": "secret"}}}})
        self.assertEqual(result.returncode, 0)
        self.assertIn("route_owner=unconfigured", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_agent_models_json_can_override_configured_route_and_default(self):
        agent_root = Path(self.tmp.name) / "agents" / "cron" / "agent"
        agent_root.mkdir(parents=True)
        agent_root.joinpath("models.json").write_text(json.dumps({
            "providers": {"litellm-cron": {
                "baseUrl": "http://172.17.0.57:4000/v1",
                "apiKey": "sk-PRIVATE_TEST_VALUE",
            }}
        }), encoding="utf-8")
        result = self.inspect({
            "models": {"providers": {"litellm-main": {
                "baseUrl": "http://172.17.0.24:4000/v1",
                "apiKey": {"source": "file", "provider": "main", "id": "value"},
            }}},
            "agents": {"defaults": {"model": {"primary": "litellm-main/qwen"}},
                       "list": [{"id": "cron", "model": "litellm-cron/gpt-4.1-mini"}]},
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("default_model_provider=litellm-main", result.stdout)
        self.assertIn("default_model_alias=qwen", result.stdout)
        self.assertIn("cron_configured_model_alias=gpt-4.1-mini", result.stdout)
        self.assertIn("cron_model_selection=agent_override", result.stdout)
        self.assertIn("cron_litellm-cron_agent_route=workstation_lan_litellm", result.stdout)
        self.assertNotIn("sk-PRIVATE_TEST_VALUE", result.stdout)



    def test_memory_search_local_secretref_points_to_workstation_instance(self):
        local_key = str(Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key")
        result = self.inspect({
            "memory": {"search": {
                "provider": "openai-compatible",
                "model": "embedding",
                "remote": {
                    "baseUrl": "http://127.0.0.1:4000/v1",
                    "apiKey": {"source": "file", "provider": "openclaw-embeddings",
                               "id": "value"},
                },
            }},
            "secrets": {"providers": {"openclaw-embeddings": {
                "source": "file", "mode": "singleValue", "path": local_key,
            }}},
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("memory_global_provider=openai-compatible", result.stdout)
        self.assertIn("memory_global_model=embedding", result.stdout)
        self.assertIn("memory_global_route_owner=workstation_litellm", result.stdout)
        self.assertIn("memory_embedding_secretref=expected", result.stdout)
        self.assertIn("memory_embedding_file_provider=expected", result.stdout)
        self.assertIn("memory_virtual_key_instance=workstation", result.stdout)
        self.assertIn("memory_runtime_secret_resolution=not_tested", result.stdout)
        self.assertNotIn(local_key, result.stdout)

    def test_memory_search_truenas_route_does_not_claim_workstation_key(self):
        confidential = "sk-private-embedding-test"
        result = self.inspect({"memory": {"search": {
            "provider": "openai-compatible",
            "model": "embedding",
            "remote": {"baseUrl": "http://172.17.0.24:4000/v1",
                       "apiKey": confidential},
        }}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("memory_global_route_owner=truenas_litellm", result.stdout)
        self.assertIn("memory_global_key_representation=literal_or_unresolved", result.stdout)
        self.assertIn("memory_virtual_key_instance=truenas", result.stdout)
        self.assertNotIn(confidential, result.stdout)

    def test_memory_provider_malformed_url_does_not_expose_private_host(self):
        result = self.inspect({"memory": {"search": {"remote": {
            "baseUrl": "http://private.example.invalid:not-a-port/v1",
            "apiKey": {"source": "file", "provider": "private-provider",
                       "id": "secret"},
        }}}})
        self.assertEqual(result.returncode, 0)
        self.assertIn("memory_global_route_owner=other_or_unverified", result.stdout)
        self.assertIn("memory_embedding_file_provider=unverified_or_different", result.stdout)
        self.assertNotIn("private-provider", result.stdout)
        self.assertNotIn("private.example.invalid", result.stdout)


if __name__ == "__main__":
    unittest.main()
