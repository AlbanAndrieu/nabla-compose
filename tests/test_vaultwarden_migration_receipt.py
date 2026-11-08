"""Offline contracts for the value-blind Vaultwarden coverage receipt."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/secrets/audit-vaultwarden-migration.py"
SPEC = importlib.util.spec_from_file_location("nabla_vaultwarden_receipt", SOURCE)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture() -> dict:
    return {
        "bootstrap": [{"app": "vaultwarden"}],
        "items": [
            {"app": "homarr", "item": "nabla/prod/homarr", "secrets": [
                {"env": "HOMARR_API_KEY"}, {"env": "POSTGRES_PASSWORD"},
            ]},
            {"app": "openrag", "item": "nabla/prod/openrag", "secrets": [
                {"env": "OPENSEARCH_PASSWORD"},
            ]},
        ],
    }


class VaultwardenMigrationReceiptTests(unittest.TestCase):
    def test_manifest_counts_without_accessing_secrets(self):
        self.assertEqual(
            module.manifest_summary(fixture()),
            {"declared_apps": 2, "declared_fields": 3, "bootstrap_entries": 1},
        )

    def test_reject_duplicate_apps(self):
        doc = fixture()
        doc["items"].append(doc["items"][0])
        with self.assertRaises(ValueError):
            module.manifest_summary(doc)

    def test_verify_reads_metadata_and_file_only(self):
        payload = json.dumps({"folder_verified": True, "apps": [
            {"app": "homarr", "status": "present"},
            {"app": "openrag", "status": "missing"},
        ]})
        calls = []
        def fake_run(argv, timeout):
            calls.append(argv)
            if argv[0] == "sudo":
                return 0, ""
            if "inventory_vaultwarden.py" in argv[1]:
                return 1, payload
            if "materialize_runtime.py" in argv[1]:
                return 0, "unsafe secret material must never be printed"
            raise AssertionError(argv)
        with patch.object(module.os, "geteuid", return_value=1000), \
             patch.dict(module.os.environ, {"BW_SESSION": "sensitive-test-value"}), \
             patch.object(module, "safe_run", side_effect=fake_run):
            rows = module.verify(fixture(), ["homarr", "openrag"])
        self.assertEqual(rows[0]["runtime_file"], "FILE_PARITY_VERIFIED")
        self.assertEqual(rows[0]["container_loaded"], "NOT_VERIFIED")
        self.assertEqual(rows[1]["runtime_file"], "UNVERIFIED")
        self.assertEqual(sum("materialize_runtime.py" in str(c) for c in calls), 1)

    def test_no_session_refuses_before_subprocess(self):
        with patch.object(module.os, "geteuid", return_value=1000), \
             patch.dict(module.os.environ, {"BW_SESSION": ""}), \
             patch.object(module, "safe_run") as safe:
            with self.assertRaises(RuntimeError):
                module.verify(fixture(), ["homarr"])
            safe.assert_not_called()

    def test_root_refuses_before_subprocess(self):
        with patch.object(module.os, "geteuid", return_value=0), \
             patch.dict(module.os.environ, {"BW_SESSION": "test"}), \
             patch.object(module, "safe_run") as safe:
            with self.assertRaises(RuntimeError):
                module.verify(fixture(), ["homarr"])
            safe.assert_not_called()

    def test_invalid_folder_rejects_parity(self):
        payload = json.dumps({"folder_verified": False, "apps": []})
        with patch.object(module.os, "geteuid", return_value=1000), \
             patch.dict(module.os.environ, {"BW_SESSION": "test"}), \
             patch.object(module, "safe_run", side_effect=[(0, ""), (1, payload)]):
            with self.assertRaises(RuntimeError):
                module.verify(fixture(), ["homarr"])

    def test_manifest_in_repo_valid(self):
        doc = json.loads((ROOT / "config/secrets/manifest.json").read_text())
        counts = module.manifest_summary(doc)
        self.assertGreater(counts["declared_apps"], 10)
        self.assertGreater(counts["declared_fields"], counts["declared_apps"])


if __name__ == "__main__":
    unittest.main()
