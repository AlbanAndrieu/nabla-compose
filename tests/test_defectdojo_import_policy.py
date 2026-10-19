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

    def test_trivy_secrets_rejected_for_allowed_producers(self):
        report = {"Results": [{"Secrets": [{"RuleID": "fixture-only"}]}]}
        for producer in ("nabla-compose", "nabla-site-alban", "fastapi-sample"):
            with self.subTest(producer=producer), self.assertRaisesRegex(ValueError, "secret evidence"):
                module.validate(producer, "Trivy Scan", json.dumps(report).encode())

    def test_fastapi_reduced_trivy_parser_allowed(self):
        report = {"Results": [{"Target": "uv.lock", "Vulnerabilities": [
            {"VulnerabilityID": "GHSA-example", "Severity": "HIGH",
             "PkgName": "fixture", "InstalledVersion": "1.0"}]}]}
        module.validate("fastapi-sample", "Trivy Scan", json.dumps(report).encode())

    def test_unlisted_service_rejected(self):
        with self.assertRaises(ValueError):
            module.validate("unapproved-repo", "Trivy Scan", b'{"Results": []}')

    def test_betterleaks_not_importable(self):
        with self.assertRaises(ValueError):
            module.validate("nabla-compose", "BetterLeaks", b'{"results": []}')

    def test_nuclei_site_hostname_must_be_exact_https(self):
        safe = b'{"template-id":"safe","matched-at":"https://www.albanandrieu.com","info":{"name":"Demo","severity":"high"}}\n'
        module.validate("nabla-site-alban", "Nuclei Scan", safe)
        for bad in (b'{"host":"https://other.example/"}\n',
                    b'{"host":"http://www.albanandrieu.com/"}\n',
                    b'{"host":"https://www.albanandrieu.com.evil.test/"}\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.validate("nabla-site-alban", "Nuclei Scan", bad)

    def test_site_trivy_import_requires_minimal_high_critical_lockfile(self):
        record = {
            "Results": [{
                "Target": "package-lock.json",
                "Vulnerabilities": [{"VulnerabilityID": "CVE-2026-1111",
                                     "PkgName": "react", "Severity": "HIGH"}],
            }],
        }
        module.validate("nabla-site-alban", "Trivy Scan", json.dumps(record).encode())
        for severity in ("LOW", "MEDIUM"):
            record["Results"][0]["Vulnerabilities"][0]["Severity"] = severity
            with self.assertRaises(ValueError):
                module.validate("nabla-site-alban", "Trivy Scan", json.dumps(record).encode())
        record["Results"][0]["Vulnerabilities"][0]["Severity"] = "HIGH"
        record["Results"][0]["Vulnerabilities"][0]["Response"] = "private secret"
        with self.assertRaises(ValueError):
            module.validate("nabla-site-alban", "Trivy Scan", json.dumps(record).encode())

    def test_nuclei_site_rejects_raw_http_evidence(self):
        safe = {
            "template-id": "safe", "matched-at": "https://www.albanandrieu.com",
            "info": {"name": "Demo", "severity": "high"},
        }
        module.validate("nabla-site-alban", "Nuclei Scan", (json.dumps(safe) + "\n").encode())
        safe["response"] = "PRIVATE_COOKIE"
        with self.assertRaises(ValueError):
            module.validate("nabla-site-alban", "Nuclei Scan", (json.dumps(safe) + "\n").encode())

    def test_codeql_requires_tool_identity(self):
        good = {"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL"}}}]}
        module.validate("nabla-compose", "CodeQL Scan", json.dumps(good).encode())
        good["runs"][0]["tool"]["driver"]["name"] = "unknown"
        with self.assertRaises(ValueError):
            module.validate("nabla-compose", "CodeQL Scan", json.dumps(good).encode())

    def test_zap_xml_is_required_and_public_domain_is_validated(self):
        good = (
            b"<?xml version='1.0'?><OWASPZAPReport><site name='https://www.albanandrieu.com'>"
            b"<alerts><alertitem><pluginid>10035</pluginid><riskcode>3</riskcode>"
            b"<instances><instance><uri>https://www.albanandrieu.com</uri>"
            b"</instance></instances></alertitem></alerts></site></OWASPZAPReport>"
        )
        module.validate("nabla-site-alban", "Zed Attack Proxy", good)
        with self.assertRaises(ValueError):
            module.validate("nabla-site-alban", "Zed Attack Proxy", b'{"site":[]}')
        with self.assertRaises(ValueError):
            module.validate(
                "nabla-site-alban", "Zed Attack Proxy",
                good.replace(b"www.albanandrieu.com", b"evil.example"),
            )
        with self.assertRaises(ValueError):
            module.validate(
                "nabla-site-alban", "Zed Attack Proxy",
                good.replace(b"</instance>", b"<requestheader>secret</requestheader></instance>"),
            )

    def test_importer_uses_policy(self):
        source = (ROOT / "scripts/security/import-scan-defectdojo.sh").read_text(encoding="utf-8")
        self.assertIn("validate-defectdojo-report.py", source)
        self.assertIn("DEFECTDOJO_IMPORT_APPROVED", source)


if __name__ == "__main__":
    unittest.main()
