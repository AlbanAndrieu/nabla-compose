from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_secret_manifest.py"
SPEC = importlib.util.spec_from_file_location("validate_secret_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SecretManifestValidationTests(unittest.TestCase):
    def test_repository_manifest_is_valid(self) -> None:
        manifest = Path(__file__).resolve().parents[1] / "config" / "secrets" / "bitwarden-map.json"
        payload = MODULE.load_manifest(manifest)
        self.assertEqual(MODULE.validate_manifest(payload), [])

    def test_duplicate_env_names_are_rejected(self) -> None:
        payload = {
            "schemaVersion": 1,
            "services": {
                "one": [
                    {
                        "env": "TOKEN",
                        "item": "nabla/homelab/one",
                        "field": "TOKEN",
                        "required": True,
                        "rotation": "rotatable",
                    }
                ],
                "two": [
                    {
                        "env": "TOKEN",
                        "item": "nabla/homelab/two",
                        "field": "TOKEN",
                        "required": True,
                        "rotation": "rotatable",
                    }
                ],
            },
        }
        errors = MODULE.validate_manifest(payload)
        self.assertTrue(any("already declared" in error for error in errors))

    def test_secret_values_do_not_belong_in_manifest_schema(self) -> None:
        payload = {
            "schemaVersion": 1,
            "services": {
                "demo": [
                    {
                        "env": "DEMO_SECRET",
                        "item": "nabla/homelab/demo",
                        "field": "SECRET",
                        "required": True,
                        "rotation": "preserve",
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = MODULE.load_manifest(path)
        self.assertNotIn("value", loaded["services"]["demo"][0])


if __name__ == "__main__":
    unittest.main()
