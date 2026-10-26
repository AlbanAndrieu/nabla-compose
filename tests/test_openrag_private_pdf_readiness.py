"""Offline contract for personal-PDF mount probe, never ingests the ticket."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/check-openrag-private-pdf.sh"


class PrivatePDFReadinessTest(unittest.TestCase):
    def test_bash_syntax(self):
        p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                           text=True, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_refuse_path_traversal_and_commands(self):
        for args in (
            [],
            ["--check", "--file", "../../escape.pdf"],
            ["--check", "--file", "/mnt/cpool/bababou/ticket.pdf"],
            ["--apply", "--file", "ticket.pdf"],
            ["--check", "--file", "ticket.txt"],
        ):
            with self.subTest(args=args):
                p = subprocess.run(["bash", str(SCRIPT), *args],
                                   capture_output=True, text=True, check=False)
                self.assertEqual(p.returncode, 2, p.stderr + p.stdout)

    def test_private_read_only_and_no_payload_extraction(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('root="/mnt/cpool/bababou"', source)
        self.assertIn('"/mnt/bababou/$basename"', source)
        self.assertIn('head -c 5', source)
        self.assertIn('http://docling:5001/ready', source)
        self.assertIn('private_pdf_bind_read_only_not_attested', source)
        self.assertIn('docling_host_not_ready', source)
        self.assertIn('docling_openrag_network_not_ready', source)
        self.assertIn('diagnose-docling-readiness.py --check', source)
        self.assertIn("NOT_TESTED: pdf_conversion_indexing_retrieval", source)
        for forbidden in ("curl -F", "convert/source", "docker cp", "base64", "--upload-file"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
