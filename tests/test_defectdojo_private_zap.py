"""Offline contracts for opt-in, private native ZAP XML ingestion."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/security/validate-defectdojo-report.py"
IMPORTER = ROOT / "scripts/security/import-scan-defectdojo.sh"
spec = importlib.util.spec_from_file_location("validate_private_zap", VALIDATOR)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

NATIVE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<OWASPZAPReport version="2.17"><site name="https://www.albanandrieu.com"
host="www.albanandrieu.com" port="443" ssl="true"><alerts><alertitem>
<pluginid>10020</pluginid><riskcode>2</riskcode>
<alert>Missing X-Frame-Options</alert>
<instances><instance><uri>https://www.albanandrieu.com/fr/contact?ref=fixture</uri>
<method>GET</method><requestheader>GET /fr/contact HTTP/1.1</requestheader>
<responseheader>HTTP/1.1 200 OK</responseheader>
</instance></instances></alertitem></alerts></site></OWASPZAPReport>"""


class PrivateZapImportContract(TestCase):
    def test_native_xml_preserves_medium_and_endpoint_in_private_mode(self):
        validator.validate("nabla-site-alban", "ZAP Scan", NATIVE_XML, private_zap_native=True)

    def test_native_xml_never_passes_through_default_minimized_contract(self):
        with self.assertRaises(ValueError):
            validator.validate("nabla-site-alban", "ZAP Scan", NATIVE_XML)

    def test_native_profile_refuses_other_producers_and_parsers(self):
        for service, scanner in [
            ("nabla-site-bababou", "ZAP Scan"),
            ("nabla-site-alban", "Trivy Scan"),
        ]:
            with self.assertRaises(ValueError):
                validator.validate(service, scanner, NATIVE_XML, private_zap_native=True)

    def test_native_profile_rejects_off_scope_urls_and_entities(self):
        cases = [
            NATIVE_XML.replace(b"www.albanandrieu.com", b"defectdojo.int.albandrieu.com"),
            NATIVE_XML.replace(b"https://www.albanandrieu.com/fr/contact",
                               b"http://www.albanandrieu.com/fr/contact"),
            NATIVE_XML.replace(b"<riskcode>2", b"<riskcode>9"),
            NATIVE_XML.replace(b"<pluginid>10020", b"<pluginid>INVALID"),
            NATIVE_XML.replace(b"<OWASPZAPReport", b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><OWASPZAPReport', 1),
        ]
        for raw in cases:
            with self.subTest(raw=raw[:70]):
                with self.assertRaises(ValueError):
                    validator.validate("nabla-site-alban", "ZAP Scan", raw, private_zap_native=True)

    def test_importer_requires_a_separate_opt_in_and_private_root_owned_inbox(self):
        importer = IMPORTER.read_text(encoding="utf8")
        for required in [
            "DEFECTDOJO_ZAP_IMPORT_PROFILE",
            "DEFECTDOJO_PRIVATE_ZAP_APPROVED",
            "/mnt/cpool/defectdojo/private-zap/site-alban",
            "--private-zap-native",
            "stat -c %u:%g",
            "stat -c %a",
            "realpath -e",
        ]:
            self.assertIn(required, importer)
        self.assertIn("DEFECTDOJO_IMPORT_APPROVED", importer)
        self.assertIn("close_old_findings=false", importer)


if __name__ == "__main__":
    main()
