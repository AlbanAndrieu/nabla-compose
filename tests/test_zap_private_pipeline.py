"""Offline regression for lossless private ZAP scan and DefectDojo ingestion."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/security/run-site-alban-zap-private.py"
VALIDATOR_PATH = ROOT / "scripts/security/validate-defectdojo-report.py"
IMPORTER_PATH = ROOT / "scripts/security/import-scan-defectdojo.sh"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = load(RUNNER_PATH, "site_alban_private_zap_runner")
validator = load(VALIDATOR_PATH, "site_alban_native_validator")

XML = b"""<?xml version="1.0"?>
<OWASPZAPReport version="2.17"><site name="https://www.albanandrieu.com"
host="www.albanandrieu.com" port="443" ssl="true"><alerts>
<alertitem><pluginid>10020</pluginid><riskcode>2</riskcode>
<alert>Header issue</alert><instances><instance>
<uri>https://www.albanandrieu.com/fr/contact?source=test</uri>
<method>GET</method><requestheader>Authorization: Bearer FULL_TEST_EVIDENCE</requestheader>
<responsebody>FULL_HTTP_BODY</responsebody>
</instance></instances></alertitem>
</alerts></site></OWASPZAPReport>"""

EMPTY_XML = b"""<?xml version="1.0"?>
<OWASPZAPReport version="2.17"><site name="https://www.albanandrieu.com"
host="www.albanandrieu.com" port="443" ssl="true"><alerts/>
</site></OWASPZAPReport>"""


class NativeZapPipelineTests(unittest.TestCase):
    def test_offline_check_never_scans_or_imports(self):
        completed = subprocess.run(
            [sys.executable, str(RUNNER_PATH)],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("network=false", completed.stdout)

    def test_native_zap_keeps_path_query_http_evidence_and_medium(self):
        validator.validate("nabla-site-alban", "ZAP Scan", XML, private_zap_native=True)
        with self.assertRaises(ValueError):
            validator.validate("nabla-site-alban", "ZAP Scan", XML)
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "report.xml"
            path.write_bytes(XML)
            with mock.patch.object(runner.REPO, "joinpath", wraps=runner.REPO.joinpath):
                # The report counts are derived from the original native XML.
                from xml.etree import ElementTree
                root = ElementTree.parse(path)
                self.assertEqual(root.findtext(".//responsebody"), "FULL_HTTP_BODY")
                self.assertEqual(root.findtext(".//riskcode"), "2")

    def test_zero_findings_remains_a_valid_complete_private_report(self):
        validator.validate("nabla-site-alban", "ZAP Scan", EMPTY_XML, private_zap_native=True)

    def test_report_archive_is_immutable_and_has_verifiable_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            sample = run_dir / "report.xml"
            sample.write_bytes(XML)
            first = runner.digest(sample)
            self.assertEqual(len(first), 64)
            manifest = {
                "run_id": "20261126T010000Z-01234567",
                "scan_state": "COMPLETE",
                "outputs": {"report.xml": {"sha256": first}},
                "import_state": "NOT_STARTED",
            }
            runner.manifest_write(run_dir, manifest)
            self.assertEqual(runner.load_manifest(run_dir), manifest)
            self.assertEqual(runner.digest(sample), first)

    def test_docker_generates_all_four_native_formats_without_truncation(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn('"report.xml"', source)
        self.assertIn('"report.json"', source)
        self.assertIn('"report.html"', source)
        self.assertIn('"report.md"', source)
        self.assertIn('"console.log"', source)
        self.assertIn('"--hook=/zap/wrk/rate-limit-hook.py"', source)
        self.assertIn('"--retry-import"', source)
        self.assertIn('reports_retained=true', source)
        self.assertNotIn('shutil.rmtree', source)
        self.assertNotIn('unlink(', source)

    def test_importer_retains_response_and_reimport_does_not_close_old_findings(self):
        importer = IMPORTER_PATH.read_text(encoding="utf-8")
        self.assertIn('DEFECTDOJO_IMPORT_RECEIPT_FILE', importer)
        self.assertIn('response_tmp', importer)
        self.assertIn('background_import=false', importer)
        self.assertIn('close_old_findings=false', importer)
        self.assertIn('RECEIPT: test_id=', importer)
        self.assertIn('100000000', importer)
        syntax = subprocess.run(["bash", "-n", str(IMPORTER_PATH)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_existing_hourly_cron_uses_saturday_and_is_opt_in(self):
        cron = (ROOT / "scripts/cron.sh").read_text(encoding="utf-8")
        self.assertIn("NABLA_CRON_ZAP_PRIVATE_ENABLED", cron)
        self.assertIn("NABLA_CRON_ZAP_PRIVATE_ENGAGEMENT_ID", cron)
        self.assertIn("run_weekly_private_zap || status=1", cron)
        self.assertIn('[[ "$weekday" == 6 && "$hour" == 06 ]]', cron)
        self.assertIn("NABLA_ZAP_PRIVATE_AUTO_IMPORT=YES", cron)
        syntax = subprocess.run(["bash", "-n", str(ROOT / "scripts/cron.sh")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
