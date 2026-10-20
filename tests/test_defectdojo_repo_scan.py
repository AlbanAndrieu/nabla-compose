"""Offline scan preparation contract; never requires Trivy, LAN or credentials."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/security/scan-repo-trivy.py"
IMPORTER = ROOT / "scripts/security/import-scan-defectdojo.sh"


class TrivyRepoDefectDojoContract(unittest.TestCase):
    def test_default_is_no_network_no_upload(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT,
            capture_output=True, text=True, check=False, timeout=8,
            env={**os.environ, "NABLA_DEFECTDOJO_SCAN_APPROVED": ""},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("network=false upload=false", result.stdout)

    def test_scan_requires_explicit_approval(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--scan"], cwd=ROOT,
            capture_output=True, text=True, check=False, timeout=8,
            env={**os.environ, "NABLA_DEFECTDOJO_SCAN_APPROVED": ""},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("approval required", result.stderr)

    def test_import_is_separate_and_lan_only(self):
        source = SCRIPT.read_text(encoding="utf-8")
        importer = IMPORTER.read_text(encoding="utf-8")
        self.assertIn('"--scanners", "vuln"', source)
        self.assertIn('"vuln,misconfig,license"', source)
        self.assertIn('"cyclonedx"', source)
        self.assertIn('audit_file', source)
        self.assertIn('sbom_file', source)
        self.assertIn("0o600", source)
        self.assertIn("10_000_000", source)
        self.assertIn('"archive", "--format=tar", "HEAD"', source)
        self.assertIn('filter="data"', source)
        self.assertNotIn("reimport-scan", source)
        self.assertIn("172.17.0.24:31085/api/v2/reimport-scan/", importer)
        self.assertIn("DEFECTDOJO_IMPORT_APPROVED", importer)


if __name__ == "__main__":
    unittest.main()
