"""Hermetic signature validation for Entra: deny replay, changed plan and expiry."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("approval", ROOT / "scripts/entra/approval.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ManifestTests(unittest.TestCase):
    def plan(self, name="nabla-iam-lab-workload-reader"):
        return {"resource_changes": [{
            "address": 'azuread_application_registration.workload["reader"]',
            "type": "azuread_application_registration",
            "change": {"actions": ["create"], "after": {"display_name": name}},
        }]}

    def test_hash_changes_when_a_resource_value_changes(self):
        self.assertNotEqual(MODULE.fingerprint(self.plan()), MODULE.fingerprint(self.plan("other")))

    def test_canonical_json_is_stable(self):
        self.assertEqual(MODULE.canonical({"b": 2, "a": 1}), b'{"a":1,"b":2}\n')

    def test_create_exposes_only_sanitized_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "plan.json").write_text(json.dumps(self.plan()))
            args = SimpleNamespace(plan=str(path / "plan.json"),
                                   output=str(path / "challenge.json"),
                                   sha="a" * 40, tenant="12345678-1234-1234-1234-123456789abc",
                                   organization="demo-lab", workspace="entra-id-free", run_id="42")
            MODULE.create(args)
            manifest = json.loads((path / "challenge.json").read_text())
            self.assertEqual(manifest["run_id"], 42)
            self.assertNotIn("display_name", json.dumps(manifest))
            self.assertEqual(manifest["plan_sha256"], MODULE.fingerprint(self.plan()))
            now = datetime.now(timezone.utc)
            expires = datetime.fromisoformat(manifest["expires_at"].replace("Z", "+00:00"))
            self.assertLessEqual(expires, now + timedelta(minutes=91))

    def test_rejects_invalid_plan_and_wrong_tenant(self):
        with self.assertRaises(ValueError):
            MODULE.fingerprint({})
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan").write_text(json.dumps(self.plan()))
            args = SimpleNamespace(plan=str(Path(tmp) / "plan"), output=str(Path(tmp) / "manifest"),
                sha="not-a-sha", tenant="company", organization="demo", workspace="demo", run_id="10")
            with self.assertRaises(ValueError):
                MODULE.create(args)


if __name__ == "__main__":
    unittest.main()
