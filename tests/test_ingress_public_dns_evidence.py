"""Offline public DNS observer: unknown and disagreement never count as absent."""
from pathlib import Path
import importlib.util
import subprocess
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ingress/collect-public-dns-evidence.py"
spec = importlib.util.spec_from_file_location("nabla_public_dns", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fake_response(status="NOERROR", answer=""):
    return subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=";; ->>HEADER<<- opcode: QUERY, status: " + status + ", id: 1\n" + answer,
        stderr=""
    )


class PublicDnsEvidenceContract(unittest.TestCase):
    def test_public_A_record_detected(self):
        with mock.patch.object(module.subprocess, "run", return_value=fake_response(
            answer="nexus.int.albandrieu.com. 60 IN A 203.0.113.1\n"
        )):
            self.assertEqual(module.resolve_query("nexus.int.albandrieu.com", "1.1.1.1", "A"), "present")

    def test_nxdomain_and_empty_noerror_are_absent_at_resolver(self):
        for response in (fake_response(status="NXDOMAIN"), fake_response(status="NOERROR")):
            with self.subTest(status=response.stdout):
                with mock.patch.object(module.subprocess, "run", return_value=response):
                    self.assertEqual(module.resolve_query("vault.int.albandrieu.com", "1.1.1.1", "AAAA"), "absent")

    def test_timeout_and_servfail_do_not_claim_absence(self):
        with mock.patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired("dig", 5)):
            self.assertEqual(module.resolve_query("s3.int.albandrieu.com", "9.9.9.9", "A"), "unknown")
        with mock.patch.object(module.subprocess, "run", return_value=fake_response(status="SERVFAIL")):
            self.assertEqual(module.resolve_query("s3.int.albandrieu.com", "9.9.9.9", "A"), "unknown")

    def test_disagreeing_recursors_are_unknown(self):
        def fake(name, resolver, rrtype):
            return "present" if resolver == "1.1.1.1" else "absent"
        with mock.patch.object(module, "resolve_query", side_effect=fake):
            self.assertEqual(module.collect(["nexus.int.albandrieu.com"])["nexus.int.albandrieu.com"], "unknown")

    def test_all_recursors_absent_means_dns_absent_only(self):
        with mock.patch.object(module, "resolve_query", return_value="absent"):
            self.assertEqual(module.collect(["vault.int.albandrieu.com"])["vault.int.albandrieu.com"], "absent")


if __name__ == "__main__":
    unittest.main()
