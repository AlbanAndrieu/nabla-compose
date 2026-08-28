from __future__ import annotations

import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "secrets" / "render_from_bitwarden.py"
SPEC = importlib.util.spec_from_file_location("render_from_bitwarden", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class SecretsRendererTests(unittest.TestCase):
    def test_repository_manifest_is_metadata_only_and_valid(self) -> None:
        manifest_path = Path(__file__).parents[1] / "config" / "secrets" / "manifest.json"
        manifest = renderer.load_manifest(manifest_path)

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(
            {item["app"] for item in manifest["items"]},
            {"2fauth", "open-terminal", "karakeep", "reactive-resume"},
        )
        serialized = json.dumps(manifest)
        self.assertNotIn('"value"', serialized)
        self.assertNotIn('"secretValue"', serialized)

    def test_manifest_rejects_duplicate_environment_variables(self) -> None:
        manifest = {
            "schemaVersion": 1,
            "server": "https://vaultwarden.example.test",
            "items": [
                {
                    "app": "one",
                    "item": "nabla/prod/one",
                    "secrets": [{"env": "API_KEY", "field": "API_KEY"}],
                },
                {
                    "app": "two",
                    "item": "nabla/prod/two",
                    "secrets": [{"env": "API_KEY", "field": "API_KEY"}],
                },
            ],
        }

        with self.assertRaises(renderer.SecretsError):
            renderer.validate_manifest(manifest)

    def test_dotenv_literal_disables_compose_interpolation(self) -> None:
        self.assertEqual(renderer.dotenv_literal("a$B${C}"), "'a$B${C}'")
        self.assertEqual(renderer.dotenv_literal("let's\\go"), "'let\\'s\\\\go'")

    def test_extract_secret_requires_exact_field(self) -> None:
        item = {
            "name": "nabla/prod/app",
            "fields": [
                {"name": "TOKEN", "value": "first"},
                {"name": "TOKEN", "value": "second"},
            ],
        }

        with self.assertRaises(renderer.SecretsError):
            renderer.extract_secret(item, {"env": "TOKEN", "field": "TOKEN"})

    def test_render_app_is_atomic_and_mode_0600(self) -> None:
        app_spec = {
            "app": "example",
            "item": "nabla/prod/example",
            "secrets": [
                {
                    "env": "EXAMPLE_TOKEN",
                    "field": "TOKEN",
                    "rotation": "preserve",
                }
            ],
        }
        item = {
            "name": "nabla/prod/example",
            "fields": [{"name": "TOKEN", "value": "abc$123"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "runtime-secrets"
            target = renderer.render_app(
                app_spec=app_spec,
                item=item,
                output_dir=output_dir,
            )

            self.assertEqual(target.read_text(encoding="utf-8").splitlines()[-1], "EXAMPLE_TOKEN='abc$123'")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output_dir.stat().st_mode), 0o700)

    def test_multiline_secret_is_rejected(self) -> None:
        item = {
            "name": "nabla/prod/app",
            "fields": [{"name": "TOKEN", "value": "line1\nline2"}],
        }

        with self.assertRaises(renderer.SecretsError):
            renderer.extract_secret(item, {"env": "TOKEN", "field": "TOKEN"})


if __name__ == "__main__":
    unittest.main()
