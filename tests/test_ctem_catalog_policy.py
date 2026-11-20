"""Offline CTEM V2 policy drift tests; no real scans or cloud access."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            "scripts/security/audit-ctem-catalog-policy.py"))


class CatalogPolicyAuditTests(unittest.TestCase):
    def setUp(self):
        self.audit = MODULE["audit_catalog"]
        self.domains = ["example.com"]
        self.lan_only = {"ollama.example.com"}

    @staticmethod
    def catalog(*entities):
        return {"schemaVersion": 2, "model": "backstage",
                "catalogRevision": "sha256:" + "a" * 64, "entities": list(entities)}

    @staticmethod
    def entity(name, hostname, visibility):
        return {"entityRef": "component:default/" + name,
                "metadata": {"annotations": {}},
                "x-nabla": {"exposure": [{"hostnames": [hostname],
                                           "visibility": visibility}]}}

    def test_detects_stale_public_intent_without_running_amass(self):
        payload = self.catalog(self.entity("ollama", "ollama.example.com", "public"))
        with patch("subprocess.run", side_effect=AssertionError("network scan forbidden")):
            report, conflicts = self.audit(payload, self.domains, self.lan_only)
        self.assertEqual(report["status"], "DECLARED_LAN_ONLY_CONFLICT")
        self.assertEqual(report["lanOnlyPublicConflictCount"], 1)
        self.assertEqual(conflicts[0]["hostname"], "ollama.example.com")
        self.assertNotIn("ollama.example.com", str(report))
        self.assertNotIn("component:default/ollama", str(report))
        self.assertEqual(report["scopeCompleteness"], "NOT_VERIFIED")

    def test_lan_intent_is_not_a_public_conflict(self):
        payload = self.catalog(self.entity("ollama", "ollama.example.com", "lan"))
        report, conflicts = self.audit(payload, self.domains, self.lan_only)
        self.assertEqual(report["status"], "DECLARED_SCOPE_NO_LAN_ONLY_CONFLICT")
        self.assertEqual(conflicts, [])

    def test_duplicate_entity_refs_fail_closed(self):
        entity = self.entity("same", "ollama.example.com", "public")
        with self.assertRaises(ValueError):
            self.audit(self.catalog(entity, entity), self.domains, self.lan_only)

    def test_malformed_catalog_fails_closed(self):
        with self.assertRaises(ValueError):
            self.audit({}, self.domains, self.lan_only)

    def test_wildcard_is_not_assigned_as_exact_match(self):
        payload = self.catalog(self.entity("service", "*.ollama.example.com", "public"))
        report, conflicts = self.audit(payload, self.domains, self.lan_only)
        self.assertEqual(report["catalogHostnameCount"], 0)
        self.assertEqual(conflicts, [])


if __name__ == "__main__":
    unittest.main()
