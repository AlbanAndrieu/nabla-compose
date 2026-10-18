"""Hermetic readiness contract: no network, Docker, API calls or secret files."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/security/check-migration-readiness.py"
SPEC = importlib.util.spec_from_file_location("migration_readiness", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
SOURCE = ROOT / "config/migrations/workstreams.json"


class MigrationReadinessContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.data = copy.deepcopy(json.loads(SOURCE.read_text(encoding="utf-8")))
        for item in self.data["workstreams"]:
            for artifact in item["artifacts"]:
                path = self.root / artifact
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n", encoding="utf-8")
        self.manifest = self.root / "config/migrations/workstreams.json"
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        self._save()

    def _save(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def test_repository_manifest_validates(self):
        self.assertEqual(audit.validate(self.data, self.root), [])

    def test_missing_evidence_is_not_runtime_acceptance(self):
        item = self.data["workstreams"][0]
        item["phase"] = "runtime_accepted"
        self.assertTrue(any("live acceptance" in x for x in audit.validate(self.data, self.root)))

    def test_missing_artifact_fails(self):
        (self.root / self.data["workstreams"][0]["artifacts"][0]).unlink()
        self.assertTrue(any("absent or unsafe artifact" in x for x in audit.validate(self.data, self.root)))

    def test_path_traversal_fails(self):
        self.data["workstreams"][1]["artifacts"] = ["../../outside"]
        self.assertTrue(any("absent or unsafe artifact" in x for x in audit.validate(self.data, self.root)))

    def test_dependency_cycle_fails(self):
        self.data["workstreams"][0]["requires"] = ["defectdojo"]
        self.assertTrue(any("dependency cycle" in x for x in audit.validate(self.data, self.root)))

    def test_unknown_and_duplicate_identifiers_fail(self):
        self.data["workstreams"][1]["id"] = "secrets-runtime"
        self.assertTrue(audit.validate(self.data, self.root))

    def test_cli_json_is_explicitly_offline(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root),
             "--manifest", str(self.manifest), "--json", "--check"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "offline-only")
        self.assertFalse(report["runtimeAccepted"])

    def test_live_root_manifest_contract(self):
        self.assertEqual(audit.validate(json.loads(SOURCE.read_text(encoding="utf-8")), ROOT), [])


if __name__ == "__main__":
    unittest.main()
