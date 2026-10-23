"""Offline contract tests for redacted OpenClaw secret audit summaries."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/check-openclaw-litellm-memory-config.py"
spec = importlib.util.spec_from_file_location("openclaw_memory_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditSummaryTests(unittest.TestCase):
    def test_known_categories(self):
        result = module.audit_summary({
            "plaintextSecrets": [{"secret": "never-display"}],
            "unresolvedRefs": [{"path": "/private"}],
            "precedenceDrift": [],
        })
        self.assertEqual(result["categories"], {
            "plaintext": 1, "unresolved": 1, "precedence_drift": 0,
        })
        self.assertNotIn("never-display", str(result))
        self.assertNotIn("/private", str(result))

    def test_unknown_schema_is_fail_closed(self):
        result = module.audit_summary({"findings": [{"token": "sensitive"}]})
        self.assertEqual(result["schema"], "unknown")
        self.assertTrue(result["unclassified"])
        self.assertNotIn("sensitive", str(result))

    def test_audit_shape_never_exposes_arbitrary_names_or_values(self):
        result = module.audit_shape({
            "top-secret-name": "sk-sensitive",
            "private-path": ["/private/secrets"],
            "metadata": {"value": "sensitive"},
            "enabled": True,
        })
        self.assertEqual(
            result, "array:1,object:1,string:1,number:0,boolean:1,null:0"
        )
        self.assertNotIn("sensitive", result)
        self.assertNotIn("private", result)

    def test_nested_shape_does_not_disclose_identifiers_or_values(self):
        result = module.audit_structure({
            "path-/home/private": [{"secret": "sk-private", "path": "/home/private"}],
            "config": {"password": "private", "findings": [1]},
            "notes": "private",
        })
        self.assertEqual(result, "array(1,0,0);object(1,0,1);scalar")
        self.assertNotIn("private", result)
        self.assertNotIn("password", result)
        self.assertNotIn("secret", result)

    def test_documented_audit_schema_counts_only(self):
        data = {
            "status": "findings",
            "summary": {
                "plaintextCount": 7, "unresolvedRefCount": 0,
                "shadowedRefCount": 1, "storeResidueCount": 2,
                "legacyResidueCount": 0,
            },
            "resolution": {"resolvabilityComplete": True},
            "findings": [{"path": "/private", "value": "sk-secret"}],
        }
        result = module.audit_v2_summary(data)
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["categories"]["plaintext"], 7)
        self.assertEqual(result["categories"]["shadowed"], 1)
        self.assertNotIn("sk-secret", str(result))
        self.assertNotIn("/private", str(result))

    def test_documented_audit_schema_rejects_missing_counts(self):
        data = {"status": "clean", "summary": {"plaintextCount": 0},
                "resolution": {"resolvabilityComplete": True}}
        self.assertIsNone(module.audit_v2_summary(data))

    def test_location_breakdown_matches_upstream_codes_only(self):
        findings = [
            {"code": "PLAINTEXT_FOUND", "file": "/private/openclaw.json",
             "jsonPath": "providers.SECRET", "provider": "PRIVATE"},
            {"code": "PLAINTEXT_FOUND", "file": "/private/.env",
             "jsonPath": "$env.TOKEN_NAME", "message": "SECRET"},
            {"code": "PLAINTEXT_FOUND", "file": "/private/agents/main/agent/openclaw-agent.sqlite",
             "jsonPath": "profiles.PRIVATE.key"},
            {"code": "PLAINTEXT_FOUND", "file": "/private/agents/main/models.json",
             "jsonPath": "providers.PRIVATE.apiKey"},
            {"code": "PLAINTEXT_FOUND", "file": "/private/other-file",
             "jsonPath": "SECRET_VALUE"},
            {"code": "LEGACY_RESIDUE", "file": "/private/agents/main/agent/openclaw-agent.sqlite",
             "jsonPath": "profiles.PRIVATE"},
            {"code": "LEGACY_RESIDUE", "file": "/private/auth.json",
             "jsonPath": "<root>"},
        ]
        data = {"findings": findings}
        v2 = {"categories": {"plaintext": 5, "legacy_residue": 2, "unresolved": 0,
                             "shadowed": 0, "store_residue": 0}}
        summary = module.audit_location_breakdown(data, v2)
        self.assertEqual(summary["plaintext"], {
            "config": 1, "dotenv": 1, "auth_store": 1,
            "generated_models": 1, "unknown": 1,
        })
        self.assertEqual(summary["legacy"], {
            "oauth_profile": 1, "legacy_file": 1, "unknown": 0,
        })
        self.assertTrue(summary["counts_match"])
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()) as output:
            self.assertTrue(module.print_audit_location_breakdown(data, v2))
        rendered = output.getvalue()
        self.assertIn("secret_audit_plaintext_location_auth_store=1", rendered)
        self.assertIn("secret_audit_legacy_location_oauth_profile=1", rendered)
        for secret in ("PRIVATE", "SECRET", "TOKEN_NAME", "/private",
                       "openclaw.json"):
            self.assertNotIn(secret, rendered)

    def test_location_mismatch_and_unrecognized_are_fail_closed(self):
        known = {"findings": [
            {"code": "PLAINTEXT_FOUND", "file": "/private/.env",
             "message": "DO_NOT_PRINT"},
        ]}
        v2 = {"categories": {
            "plaintext": 16, "unresolved": 0, "shadowed": 0,
            "store_residue": 0, "legacy_residue": 2,
        }}
        result = module.audit_location_breakdown(known, v2)
        self.assertFalse(result["counts_match"])
        self.assertIsNone(module.audit_location_breakdown(
            {"findings": [{"code": "SECRET_NEW_CODE", "file": "/private"}]}, v2))
        self.assertIsNone(module.audit_location_breakdown(
            {"findings": ["/private"]}, v2))
        self.assertIsNone(module.audit_location_breakdown(
            {"findings": "SECRET"}, v2))
        self.assertIsNone(module.audit_location_breakdown(
            {"findings": [{}] * 10001}, v2))

    def test_location_categories_with_no_path_are_unknown(self):
        data = {"findings": [
            {"code": "PLAINTEXT_FOUND", "file": None},
            {"code": "LEGACY_RESIDUE", "file": "/private/key"},
        ]}
        v2 = {"categories": {"plaintext": 1, "legacy_residue": 1,
                             "unresolved": 0, "shadowed": 0,
                             "store_residue": 0}}
        summary = module.audit_location_breakdown(data, v2)
        self.assertEqual(summary["plaintext"]["unknown"], 1)
        self.assertEqual(summary["legacy"]["unknown"], 1)

    def test_owner_breakdown_is_bounded_and_redacted(self):
        from contextlib import redirect_stdout
        from io import StringIO
        rows = [
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/agents/main/agent/openclaw-agent.sqlite",
             "provider": "SECRET"},
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/agents/cron/agent/openclaw-agent.sqlite"},
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/state.db"},
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/agents/main/agent/models.json"},
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/agents/cron/agent/models.json"},
            {"code": "LEGACY_RESIDUE", "file": "/PRIVATE/agents/main/agent/auth.json",
             "jsonPath": "<root>"},
            {"code": "LEGACY_RESIDUE", "file": "/PRIVATE/auth.json",
             "jsonPath": "<root>"},
        ]
        v2 = {"categories": {
            "plaintext": 5, "legacy_residue": 2, "unresolved": 0,
            "shadowed": 0, "store_residue": 0,
        }}
        result = module.audit_owner_breakdown({"findings": rows}, v2)
        self.assertEqual(result["auth_store"], {
            "main": 1, "cron": 1, "other_or_shared": 1})
        self.assertEqual(result["generated_models"], {
            "main": 1, "cron": 1, "other_or_shared": 0})
        self.assertEqual(result["legacy_file"], {
            "main": 1, "cron": 0, "other_or_shared": 1})
        with redirect_stdout(StringIO()) as printed:
            self.assertTrue(module.print_audit_owner_breakdown({"findings": rows}, v2))
        self.assertIn("secret_audit_owner_counts_match=true", printed.getvalue())
        for value in ("PRIVATE", "SECRET", "/agents", "auth.json"):
            self.assertNotIn(value, printed.getvalue())

    def test_owner_breakdown_refuses_mismatch_and_unknown_schema(self):
        data = {"findings": [
            {"code": "PLAINTEXT_FOUND", "file": "/PRIVATE/other.sqlite"},
        ]}
        v2 = {"categories": {
            "plaintext": 1, "legacy_residue": 0, "unresolved": 0,
            "shadowed": 0, "store_residue": 0,
        }}
        self.assertEqual(module.audit_owner_breakdown(data, v2)["auth_store"][
            "other_or_shared"], 1)
        bad = {"categories": {**v2["categories"], "plaintext": 2}}
        self.assertIsNone(module.audit_owner_breakdown(data, bad))
        self.assertIsNone(module.audit_owner_breakdown(
            {"findings": [{"code": "UNKNOWN", "file": "/PRIVATE"}]}, v2))

    def test_invalid_or_boolean_counts_not_accepted(self):
        result = module.audit_summary({"plaintext": True})
        self.assertEqual(result["schema"], "unknown")


if __name__ == "__main__":
    unittest.main()
