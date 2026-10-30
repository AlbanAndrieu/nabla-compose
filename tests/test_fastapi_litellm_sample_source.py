"""Offline, value-blind contracts for the FastAPI application key source check."""
import contextlib
import importlib.util
import io
import os
import json
import subprocess
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/secrets/check-fastapi-litellm-sample-source.py"

# Do not require the Bitwarden/jsonschema runtime during offline contract tests.
fake_module = types.ModuleType("render_from_bitwarden")
fake_module.BitwardenClient = MagicMock()
fake_module.SecretsError = type("SecretsError", (RuntimeError,), {})
fake_module.load_manifest = MagicMock()
spec = importlib.util.spec_from_file_location("fastapi_sample_source", SRC)
mod = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"render_from_bitwarden": fake_module}):
    spec.loader.exec_module(mod)


def item(*fields):
    return {"name": mod.ITEM, "fields": list(fields)}


def field(value="sk-SYNTHETIC-NOT-A-KEY", field_type=1):
    return {"name": mod.FIELD, "type": field_type, "value": value}


class FastApiSampleSourceTests(unittest.TestCase):
    def test_field_states_never_return_values(self):
        fixtures = (
            (item(field()), "field_present_nonempty_hidden"),
            (item(), "field_absent"),
            (item(field("")), "field_empty"),
            (item(field("  ")), "field_empty"),
            (item(field(field_type=0)), "field_not_hidden"),
            (item(field(), field()), "field_duplicate"),
            (item(field("SYNTHETIC\nINJECTION")), "field_invalid_format"),
            (item(field("SYNTHETIC\x00INJECTION")), "field_invalid_format"),
            ({"fields": "PRIVATE-SYNTHETIC"}, "field_unverified"),
        )
        for fixture, expected in fixtures:
            with self.subTest(expected=expected):
                value = mod.classify(fixture)
                self.assertEqual(value, expected)
                self.assertNotIn("SYNTHETIC", value)

    def test_source_check_requires_unprivileged_unlocked_operator(self):
        with patch.object(mod.os, "geteuid", return_value=0):
            self.assertEqual(mod.check(), "unprivileged_operator_required")
        with patch.object(mod.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"BW_SESSION": ""}), \
             patch.object(mod, "BitwardenClient") as client:
            self.assertEqual(mod.check(), "vaultwarden_session_unavailable")
            client.assert_not_called()

    def test_source_resolves_exact_manifest_item_folder_and_field(self):
        manifest = {
            "server": "https://example.invalid",
            "folder": {"id": "synthetic-folder-id", "name": "TrueNAS"},
            "items": [{
                "app": "sample-litellm", "item": "nabla/prod/sample-litellm",
                "secrets": [{"env": mod.FIELD, "field": mod.FIELD}],
            }],
        }
        client = MagicMock()
        client.get_exact_item.return_value = item(field())
        with patch.object(mod.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"BW_SESSION": "SYNTHETIC-SESSION"}), \
             patch.object(mod, "load_manifest", return_value=manifest), \
             patch.object(mod, "BitwardenClient", return_value=client) as factory:
            result = mod.check()
        self.assertEqual(result, "field_present_nonempty_hidden")
        factory.assert_called_once_with(session="SYNTHETIC-SESSION",
                                        server="https://example.invalid")
        client.verify_folder.assert_called_once_with("synthetic-folder-id", "TrueNAS")
        client.get_exact_item.assert_called_once_with("nabla/prod/sample-litellm",
                                                       "synthetic-folder-id")

    def test_manifest_drift_blocks_source_lookup(self):
        manifest = {
            "server": "https://example.invalid",
            "folder": {"id": "synthetic-folder-id", "name": "TrueNAS"},
            "items": [{
                "app": "litellm", "item": "WRONG-ITEM",
                "secrets": [{"env": mod.FIELD, "field": mod.FIELD}],
            }],
        }
        with patch.object(mod.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"BW_SESSION": "SYNTHETIC-SESSION"}), \
             patch.object(mod, "load_manifest", return_value=manifest), \
             patch.object(mod, "BitwardenClient") as client:
            self.assertEqual(mod.check(), "manifest_mismatch")
            client.assert_not_called()

    def test_entrypoint_outputs_only_metadata_and_fails_closed(self):
        with patch.object(mod, "check", return_value="field_present_nonempty_hidden"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mod.main(["--check"]), 0)
        self.assertIn('"field_state": "field_present_nonempty_hidden"', out.getvalue())
        self.assertIn('"service_runtime_mutated": false', out.getvalue())
        self.assertIn('"model_requests_sent": 0', out.getvalue())
        self.assertNotIn("SYNTHETIC", out.getvalue())

        with patch.object(mod, "check", return_value="field_absent"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mod.main(["--check"]), 2)
        self.assertIn('"field_state": "field_absent"', out.getvalue())


    def test_missing_jsonschema_returns_dependency_class_without_traceback(self):
        env = dict(os.environ)
        env["BW_SESSION"] = "SYNTHETIC-SESSION-NO-NETWORK"
        # -S disables site-packages so the import cannot see jsonschema.
        result = subprocess.run(
            [sys.executable, "-S", str(SRC), "--check"],
            env=env, capture_output=True, text=True, timeout=5, check=False
        )
        self.assertEqual(result.returncode, 2)
        data = json.loads(result.stdout)
        self.assertEqual(data["field_state"], "python_dependency_unavailable")
        self.assertEqual(data["service_runtime_mutated"], False)
        self.assertEqual(data["secret_values_printed"], False)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("SYNTHETIC-SESSION-NO-NETWORK", result.stdout)
        self.assertNotIn("SYNTHETIC-SESSION-NO-NETWORK", result.stderr)

    def test_secret_provider_exception_is_redacted(self):
        with patch.object(mod, "check", side_effect=mod.SecretsError(
                "SECRET-NEVER-PRINT")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mod.main(["--check"]), 2)
        self.assertIn('"field_state": "vaultwarden_unverified"', out.getvalue())
        self.assertNotIn("SECRET-NEVER-PRINT", out.getvalue())


    def test_vaultwarden_stages_are_redacted(self):
        manifest = {"server": "https://example.invalid",
            "folder": {"id": "synthetic-folder", "name": "TrueNAS"},
            "items": [{"app": mod.APP, "item": mod.ITEM,
                       "secrets": [{"env": mod.FIELD, "field": mod.FIELD}]}]}
        for method, expected in (
            ("verify", "vaultwarden_verify_failed"),
            ("verify_folder", "vaultwarden_folder_failed"),
            ("get_exact_item", "vaultwarden_item_lookup_failed"),
        ):
            with self.subTest(method=method):
                client = MagicMock()
                getattr(client, method).side_effect = mod.SecretsError("SECRET-NEVER-PRINT")
                with patch.object(mod.os, "geteuid", return_value=1000), \
                     patch.dict(os.environ, {"BW_SESSION": "SYNTHETIC-SESSION"}), \
                     patch.object(mod, "load_manifest", return_value=manifest), \
                     patch.object(mod, "BitwardenClient", return_value=client):
                    self.assertEqual(mod.check(), expected)


if __name__ == "__main__":
    unittest.main()
