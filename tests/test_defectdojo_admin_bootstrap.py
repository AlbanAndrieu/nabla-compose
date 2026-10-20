"""DefectDojo UI credential bootstrap: no real Vaultwarden or TrueNAS access."""

from __future__ import annotations

import contextlib
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from types import ModuleType
from unittest import TestCase, main, mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/secrets/bootstrap_defectdojo_admin.py"
SPEC = importlib.util.spec_from_file_location("dojo_initial_admin", SOURCE)
assert SPEC and SPEC.loader
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)


class VaultClient:
    def __init__(self, **kwargs):
        pass

    def verify(self):
        pass

    def verify_folder(self, folder_id, folder_name):
        pass


class DefectDojoBootstrapTests(TestCase):
    def run_case(self, existing, *, apply=True):
        writes = []
        importer = ModuleType("import_env_to_bitwarden")
        importer.exact_items = lambda *_a, **_kw: existing
        importer.create_item = lambda _c, payload: writes.append(("create", payload))
        importer.edit_item = lambda _c, **kw: writes.append(("edit", kw["payload"]))
        importer.sync_after_write = lambda _c, _names: True

        renderer = ModuleType("render_from_bitwarden")
        renderer.SecretsError = type("SecretsError", (Exception,), {})
        renderer.BitwardenClient = VaultClient
        renderer.load_manifest = lambda _path: {
            "server": "https://vaultwarden.example.invalid",
            "folder": {"id": "fixture", "name": "TrueNAS"},
            "items": [{"app": "defectdojo", "item": "nabla/prod/defectdojo",
                       "secrets": [{"env": "DD_ADMIN_USER"}, {"env": "DD_ADMIN_PASSWORD"}]}],
        }
        output = StringIO()
        with (
            mock.patch.dict(sys.modules, {
                "import_env_to_bitwarden": importer,
                "render_from_bitwarden": renderer,
            }),
            mock.patch.object(SCRIPT.os, "geteuid", return_value=1000),
            mock.patch.object(SCRIPT.os, "environ", {"BW_SESSION": "fixture-session"}),
            mock.patch.object(sys, "argv", [str(SOURCE), "--apply" if apply else "--check"]),
            contextlib.redirect_stdout(output),
        ):
            result = SCRIPT.main()
        return result, writes, output.getvalue()

    def test_first_time_item_created_without_existing_db(self):
        result, writes, output = self.run_case([])
        self.assertEqual(result, 0)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][0], "create")
        login = writes[0][1]["login"]
        self.assertEqual(login["username"], "nabla")
        self.assertGreaterEqual(len(login["password"]), 64)
        self.assertNotIn(login["password"], output)

    def test_existing_keys_preserved_when_login_missing(self):
        original = {"id": "fixture-id", "login": {"username": "nabla"},
                    "fields": [{"name": "DD_SECRET_KEY", "value": "not-real"}]}
        result, writes, _ = self.run_case([original])
        self.assertEqual(result, 0)
        self.assertEqual(writes[0][0], "edit")
        self.assertEqual(writes[0][1]["fields"], original["fields"])

    def test_never_rotates_existing_ui_password(self):
        original = {"id": "fixture-id", "login": {"username": "nabla", "password": "existing"}}
        result, writes, output = self.run_case([original])
        self.assertEqual(result, 0)
        self.assertFalse(writes)
        self.assertIn("EXISTS", output)

    def test_existing_admin_login_with_password_requires_manual_reconciliation(self):
        original = {"id": "old", "login": {"username": "admin", "password": "existing"}}
        importer = ModuleType("import_env_to_bitwarden")
        importer.exact_items = lambda *_a, **_kw: [original]
        importer.create_item = lambda *_a, **_kw: self.fail("unexpected create")
        importer.edit_item = lambda *_a, **_kw: self.fail("unexpected edit")
        importer.sync_after_write = lambda *_a, **_kw: self.fail("unexpected sync")
        renderer = ModuleType("render_from_bitwarden")
        renderer.SecretsError = type("SecretsError", (Exception,), {})
        renderer.BitwardenClient = VaultClient
        renderer.load_manifest = lambda _path: {
            "server": "https://vaultwarden.example.invalid",
            "folder": {"id": "fixture", "name": "TrueNAS"},
            "items": [{"app": "defectdojo", "item": "nabla/prod/defectdojo",
                       "secrets": [{"env": "DD_ADMIN_USER"}, {"env": "DD_ADMIN_PASSWORD"}]}],
        }
        with (
            mock.patch.dict(sys.modules, {
                "import_env_to_bitwarden": importer,
                "render_from_bitwarden": renderer,
            }),
            mock.patch.object(SCRIPT.os, "geteuid", return_value=1000),
            mock.patch.object(SCRIPT.os, "environ", {"BW_SESSION": "fixture-session"}),
            mock.patch.object(sys, "argv", [str(SOURCE), "--apply"]),
        ):
            with self.assertRaises(renderer.SecretsError):
                SCRIPT.main()

    def test_dry_run_never_loads_credentials(self):
        output = StringIO()
        with (mock.patch.object(sys, "argv", [str(SOURCE), "--check"]),
              contextlib.redirect_stdout(output)):
            self.assertEqual(SCRIPT.main(), 0)
        self.assertIn("CHECK", output.getvalue())


if __name__ == "__main__":
    main()
