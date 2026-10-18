"""Fail-closed private DefectDojo importer examples without network use."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/security/validate-defectdojo-report.py"
spec = importlib.util.spec_from_file_location("validate_dojo", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DefectDojoImportPolicyTests(unittest.TestCase):
    def test_valid_trivy_for_compose(self):
        module.validate("nabla-compose", "Trivy Scan", b'{"Results": []}')

    def test_unlisted_service_rejected(self):
        with self.assertRaises(ValueError):
            module.validate("unapproved-repo", "Trivy Scan", b'{"Results": []}')

    def test_betterleaks_not_importable(self):
        with self.assertRaises(ValueError):
            module.validate("nabla-compose", "BetterLeaks", b'{"results": []}')

    def test_nuclei_site_hostname_must_be_exact_https(self):
        safe = b'{"host":"https://www.albanandrieu.com/","matched-at":"https://www.albanandrieu.com/"}\n'
        module.validate("nabla-site-alban", "Nuclei Scan", safe)
        for bad in (b'{"host":"https://other.example/"}\n',
                    b'{"host":"http://www.albanandrieu.com/"}\n',
                    b'{"host":"https://www.albanandrieu.com.evil.test/"}\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.validate("nabla-site-alban", "Nuclei Scan", bad)

    def test_codeql_requires_tool_identity(self):
        good = {"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL"}}}]}
        module.validate("nabla-compose", "CodeQL Scan", json.dumps(good).encode())
        good["runs"][0]["tool"]["driver"]["name"] = "unknown"
        with self.assertRaises(ValueError):
            module.validate("nabla-compose", "CodeQL Scan", json.dumps(good).encode())

    def test_zap_cross_domain_rejected(self):
        good = {"site":[{"@name":"https://www.albanandrieu.com"}]}
        module.validate("nabla-site-alban", "Zed Attack Proxy", json.dumps(good).encode())
        good["site"][0]["@name"] = "https://bad.example"
        with self.assertRaises(ValueError):
            module.validate("nabla-site-alban", "Zed Attack Proxy", json.dumps(good).encode())

    def test_importer_uses_policy(self):
        source = (ROOT / "scripts/security/import-scan-defectdojo.sh").read_text(encoding="utf-8")
        self.assertIn("validate-defectdojo-report.py", source)
        self.assertIn("DEFECTDOJO_IMPORT_APPROVED", source)


if __name__ == "__main__":
    unittest.main()
