"""Hermetic, no-network tests for Workstation LiteLLM ↔ Vaultwarden source equality."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/secrets/inspect-fastapi-workstation-key-vaultwarden.py"

fake = types.ModuleType("render_from_bitwarden")
fake.BitwardenClient = MagicMock
fake.SecretsError = type("SecretsError", (RuntimeError,), {})
fake.load_manifest = MagicMock()
spec = importlib.util.spec_from_file_location("fastapi_vaultwarden_compare", SCRIPT)
module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"render_from_bitwarden": fake}):
    spec.loader.exec_module(module)


class ReadonlyKeyCompareTests(unittest.TestCase):
    def private_file(self, root: Path, mode: int = 0o600):
        path = root / module.KEY_PATH
        path.parent.mkdir(parents=True)
        for parent in (root / ".local", root / ".local/share",
                       root / ".local/share/nabla-compose", path.parent):
            os.chmod(parent, 0o700)
        path.write_text("sk-SYNTHETIC-NEVER-PRINT\n")
        os.chmod(path, mode)
        return path

    def test_private_file_must_be_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.private_file(root)
            self.assertEqual(module.read_private_key(root),
                             "sk-SYNTHETIC-NEVER-PRINT")
            os.chmod(path, 0o644)
            with self.assertRaises(module.Blocked):
                module.read_private_key(root)

    def test_symlink_key_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.private_file(root)
            other = path.parent / "other.key"
            path.rename(other)
            path.symlink_to(other)
            with self.assertRaises(module.Blocked):
                module.read_private_key(root)

    def test_unsafe_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.private_file(root)
            os.chmod(root / ".local/share/nabla-compose/fastapi-litellm",
                     0o777)
            with self.assertRaises(module.Blocked):
                module.read_private_key(root)

    def test_only_exact_hidden_field_matches(self):
        source = "sk-SYNTHETIC-NEVER-PRINT"
        base = {"fields": [{"name": module.FIELD, "value": source, "type": 1}]}
        self.assertEqual(module.inspect(base, source), "field_matches_private_key")
        self.assertEqual(module.inspect(base, "sk-ANOTHER"), "field_mismatch_no_overwrite")
        self.assertEqual(module.inspect({"fields": []}, source), "field_absent")
        self.assertEqual(module.inspect({"fields": None}, source), "field_absent")
        self.assertEqual(module.inspect({"fields": "invalid"}, source),
                         "field_unverified_schema")
        self.assertEqual(module.inspect({"fields": [
            {"name": module.FIELD, "value": source, "type": 0}]}, source),
            "field_not_hidden")
        self.assertEqual(module.inspect({"fields": [
            {"name": module.FIELD, "value": source, "type": 1},
            {"name": module.FIELD, "value": source, "type": 1},
        ]}, source), "field_duplicate")
        self.assertEqual(module.inspect({"fields": [
            {"name": module.FIELD, "value": "a\nb", "type": 1},
        ]}, source), "field_invalid_format")

    def test_manifest_restricts_target_and_folder(self):
        doc = {"folder": {"id": "synthetic", "name": "TrueNAS"},
               "items": [{"app": "litellm", "item": module.ITEM,
                          "secrets": [{"env": module.FIELD, "field": module.FIELD}]}]}
        self.assertEqual(module.manifest_contract(doc), ("synthetic", "TrueNAS"))
        doc["folder"]["name"] = "Other"
        with self.assertRaises(module.Blocked):
            module.manifest_contract(doc)

    def test_no_session_fails_before_key_read_or_network(self):
        with patch.object(module.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"BW_SESSION": ""}), \
             patch.object(module, "read_private_key") as local_key, \
             patch.object(module, "BitwardenClient") as client:
            self.assertEqual(module.check(), "fresh_session_required")
            local_key.assert_not_called()
            client.assert_not_called()

    def test_authenticated_read_only_can_attest_equality(self):
        manifest = {"server": "https://synthetic.invalid",
                    "folder": {"id": "synthetic-folder", "name": "TrueNAS"},
                    "items": [{"app": "litellm", "item": module.ITEM,
                               "secrets": [{"env": module.FIELD, "field": module.FIELD}]}]}
        client = MagicMock()
        client.get_exact_item.return_value = {
            "fields": [{"name": module.FIELD,
                        "value": "sk-SYNTHETIC-NEVER-PRINT", "type": 1}]}
        with patch.object(module.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"BW_SESSION": "SYNTHETIC-SESSION"}), \
             patch.object(module, "read_private_key",
                          return_value="sk-SYNTHETIC-NEVER-PRINT"), \
             patch.object(module, "load_manifest", return_value=manifest), \
             patch.object(module, "BitwardenClient", return_value=client):
            self.assertEqual(module.check(), "field_matches_private_key")
        client.verify.assert_called_once()
        client.verify_folder.assert_called_once_with("synthetic-folder", "TrueNAS")
        client.get_exact_item.assert_called_once_with(module.ITEM, "synthetic-folder")
        self.assertNotIn("edit", [entry[0] for entry in client.method_calls])
        self.assertNotIn("create", [entry[0] for entry in client.method_calls])

    def test_cli_exceptions_never_leak_credentials(self):
        with patch.object(module, "check",
                          side_effect=module.SecretsError("sk-SHOULD-NOT-PRINT")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(["--check"]), 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["field_state"], "vaultwarden_unverified")
        self.assertFalse(report["vaultwarden_written"])
        self.assertFalse(report["runtime_mutated"])
        self.assertFalse(report["secret_values_printed"])
        self.assertNotIn("sk-", output.getvalue())

    def test_no_apply_entrypoint_and_redacted_output(self):
        with patch.object(module, "check", return_value="field_matches_private_key"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(module.main(["--check"]), 0)
        self.assertEqual(json.loads(output.getvalue())["field_state"],
                         "field_matches_private_key")
        source = SCRIPT.read_text()
        self.assertNotIn("bw edit", source)
        self.assertNotIn("bw create", source)
        self.assertNotIn('method="POST"', source)
        self.assertNotIn("--apply", source)


if __name__ == "__main__":
    unittest.main()
