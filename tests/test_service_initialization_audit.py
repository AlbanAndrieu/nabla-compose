from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "truenas" / "audit-service-initialization.py"
SPEC = importlib.util.spec_from_file_location("audit_service_initialization", MODULE)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ServiceInitializationAuditTests(unittest.TestCase):
    def test_declared_apps_prefers_explicit_runtime_app_id(self) -> None:
        original_root = audit.ROOT
        audit.ROOT = ROOT
        try:
            rows = audit.declared_apps(
                {
                    "services": [
                        {
                            "id": "2fauth",
                            "sourcePath": "apps/2fauth/compose.yml",
                            "runtime": {
                                "provider": "truenas-app",
                                "appId": "twofactor-auth",
                            },
                        }
                    ]
                }
            )
        finally:
            audit.ROOT = original_root

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["app"], "2fauth")
        self.assertEqual(rows[0]["runtimeId"], "twofactor-auth")
        self.assertEqual(rows[0]["status"], "active")

    def test_recommendation_blocks_missing_app_on_secret_debt(self) -> None:
        row = {
            "mappingError": None,
            "manual": False,
            "state": "MISSING",
            "unmanagedSecretVariables": ["demo|TOKEN|source"],
            "legacyEnvFiles": [],
            "manifestManaged": False,
            "canonicalSecret": {"present": False},
            "insecureDefaults": [],
        }
        self.assertEqual(audit.recommend(row), "secrets-first")

    def test_manual_profile_is_not_treated_as_missing_daemon(self) -> None:
        row = {
            "mappingError": None,
            "manual": True,
            "state": "MISSING",
            "unmanagedSecretVariables": [],
            "legacyEnvFiles": [],
            "manifestManaged": True,
            "canonicalSecret": {"present": False},
            "insecureDefaults": [],
        }
        self.assertEqual(audit.recommend(row), "manual-job")

    def test_planned_and_disabled_intent_suppress_initialization_actions(self) -> None:
        base = {
            "mappingError": None,
            "statusError": None,
            "manual": False,
            "state": "MISSING",
            "unmanagedSecretVariables": [],
            "legacyEnvFiles": [],
            "manifestManaged": False,
            "canonicalSecret": {"present": False},
            "insecureDefaults": [],
        }

        self.assertEqual(audit.recommend({**base, "status": "planned"}), "planned")
        self.assertEqual(audit.recommend({**base, "status": "disabled"}), "disabled")


if __name__ == "__main__":
    unittest.main()
