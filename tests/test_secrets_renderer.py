from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "secrets" / "render_from_bitwarden.py"
SPEC = importlib.util.spec_from_file_location("render_from_bitwarden", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

IMPORT_PATH = ROOT / "scripts" / "secrets" / "import_env_to_bitwarden.py"
IMPORT_SPEC = importlib.util.spec_from_file_location("import_env_to_bitwarden", IMPORT_PATH)
assert IMPORT_SPEC and IMPORT_SPEC.loader
with mock.patch.dict("sys.modules", {"render_from_bitwarden": renderer}):
    importer = importlib.util.module_from_spec(IMPORT_SPEC)
    IMPORT_SPEC.loader.exec_module(importer)


class SecretsRendererTests(unittest.TestCase):
    def test_repository_manifest_is_metadata_only_and_valid(self) -> None:
        manifest_path = ROOT / "config" / "secrets" / "manifest.json"
        manifest = renderer.load_manifest(manifest_path)

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["folder"]["name"], "TrueNAS")
        self.assertEqual(
            manifest["folder"]["id"],
            "44a92b83-2762-4fa5-a238-f84396fd26f9",
        )
        self.assertEqual(
            {item["app"] for item in manifest["items"]},
            {
                "infrastructure-bootstrap",
                "grafana-observability",
                "pfsense-observability",
                "n8n",
                "2fauth",
                "open-terminal",
                "karakeep",
                "reactive-resume",
            },
        )
        serialized = json.dumps(manifest)
        self.assertNotIn('"value"', serialized)
        self.assertNotIn('"secretValue"', serialized)

    def test_manifest_rejects_duplicate_environment_variables(self) -> None:
        manifest = {
            "schemaVersion": 1,
            "server": "https://vaultwarden.example.test",
            "folder": {"name": "TrueNAS", "id": "folder-id"},
            "items": [
                {
                    "app": "one",
                    "item": "one",
                    "secrets": [{"env": "API_KEY", "field": "API_KEY"}],
                },
                {
                    "app": "two",
                    "item": "two",
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

            self.assertEqual(
                target.read_text(encoding="utf-8").splitlines()[-1],
                "EXAMPLE_TOKEN='abc$123'",
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output_dir.stat().st_mode), 0o700)

    def test_multiline_secret_is_rejected(self) -> None:
        item = {
            "name": "nabla/prod/app",
            "fields": [{"name": "TOKEN", "value": "line1\nline2"}],
        }

        with self.assertRaises(renderer.SecretsError):
            renderer.extract_secret(item, {"env": "TOKEN", "field": "TOKEN"})

    @mock.patch.object(renderer.subprocess, "run")
    def test_bw_session_is_passed_in_environment_not_argv(self, run: mock.Mock) -> None:
        run.return_value.stdout = "ok\n"
        client = renderer.BitwardenClient(
            session="session-secret",
            server="https://vaultwarden.example.test",
        )

        client._run("sync", with_session=True)

        command = run.call_args.args[0]
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(command, ["bw", "sync"])
        self.assertNotIn("session-secret", command)
        self.assertEqual(child_env["BW_SESSION"], "session-secret")

    @mock.patch.object(renderer.subprocess, "run")
    def test_item_lookup_is_scoped_to_folder(self, run: mock.Mock) -> None:
        run.return_value.stdout = json.dumps(
            [{"name": "TOKEN", "folderId": "folder-id", "login": {"password": "x"}}]
        )
        client = renderer.BitwardenClient(
            session="session-secret",
            server="https://vaultwarden.example.test",
        )

        client.get_exact_item("TOKEN", "folder-id")
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            ["bw", "list", "items", "--search", "TOKEN", "--folderid", "folder-id"],
        )

    def test_importer_reads_current_environment_without_parsing_shell_files(self) -> None:
        app_spec = {
            "app": "example",
            "item": "example",
            "secrets": [
                {
                    "env": "TARGET_TOKEN",
                    "importEnv": "LEGACY_EXPORTED_TOKEN",
                    "field": "TOKEN",
                }
            ],
        }
        with mock.patch.dict(os.environ, {"LEGACY_EXPORTED_TOKEN": "secret-value"}, clear=False):
            values = importer.collect_values(app_spec)
        self.assertEqual(values, {"TARGET_TOKEN": "secret-value"})

    def test_importer_builds_hidden_custom_fields(self) -> None:
        app_spec = {
            "app": "example",
            "item": "example",
            "secrets": [{"env": "TOKEN", "field": "TOKEN"}],
        }
        item = importer.make_item(
            app_spec=app_spec,
            folder_id="folder-id",
            values={"TOKEN": "secret-value"},
        )
        self.assertEqual(item["folderId"], "folder-id")
        self.assertEqual(item["fields"][0]["name"], "TOKEN")
        self.assertEqual(item["fields"][0]["type"], 1)
        self.assertEqual(item["fields"][0]["value"], "secret-value")


if __name__ == "__main__":
    unittest.main()
