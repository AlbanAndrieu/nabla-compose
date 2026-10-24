"""Offline OpenRAG secret migration contract. No credential values are read."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OpenragSecretMetadataTest(unittest.TestCase):
    def test_openrag_consumer_keys_are_declared_without_values(self):
        manifest = json.loads(
            (ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8")
        )
        matches = [item for item in manifest["items"] if item["app"] == "openrag"]
        self.assertEqual(len(matches), 1)
        entry = matches[0]
        self.assertEqual(entry["item"], "nabla/prod/openrag")
        self.assertEqual(
            {secret["env"] for secret in entry["secrets"]},
            {"OPENSEARCH_PASSWORD", "LITELLM_IDE_API_KEY"},
        )
        for secret in entry["secrets"]:
            self.assertEqual(secret["rotation"], "preserve")
            self.assertEqual(secret["field"], secret["env"])
            self.assertNotIn("value", secret)
            self.assertNotIn("password", secret)

    def test_openrag_provider_password_is_not_independently_rotated(self):
        manifest = json.loads(
            (ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8")
        )
        opensearch = next(
            x for x in manifest["items"] if x["app"] == "opensearch"
        )
        shared = next(
            secret for secret in opensearch["secrets"]
            if secret["env"] == "OPENSEARCH_PASSWORD"
        )
        self.assertEqual(shared["rotation"], "preserve")

    def test_runner_does_not_apply_secret_migration_as_a_check(self):
        script = (
            ROOT / "scripts/truenas/finish-migrations-20261024.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "bootstrap-repository-env-files.sh --check openrag", script,
        )
        self.assertIn(
            "bootstrap-repository-env-files.sh --check akvorado", script,
        )
        self.assertIn("reconcile-openrag-opensearch-secret.sh --check", script)


if __name__ == "__main__":
    unittest.main()
