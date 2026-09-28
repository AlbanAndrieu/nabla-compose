from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENOVATE = ROOT / "renovate.json"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
RENOVATE_WORKFLOW = ROOT / ".github" / "workflows" / "renovate.yml"


class RenovateConfigContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(RENOVATE.read_text(encoding="utf-8"))

    def test_renovate_is_single_routine_update_producer(self) -> None:
        self.assertFalse(
            DEPENDABOT.exists(),
            ".github/dependabot.yml must stay absent so Dependabot version updates do not compete with Renovate",
        )
        self.assertTrue(RENOVATE_WORKFLOW.exists())

    def test_security_alert_label_is_additive(self) -> None:
        extends = self.config["extends"]
        self.assertIn(
            ":enableVulnerabilityAlertsWithAdditionalLabel('security')",
            extends,
        )
        self.assertNotIn(
            ":enableVulnerabilityAlertsWithLabel('security')",
            extends,
        )
        self.assertEqual(self.config["labels"], ["dependencies", "renovate"])

    def test_security_remediation_is_immediate_but_bounded(self) -> None:
        self.assertEqual(self.config["minimumReleaseAge"], "7 days")
        vulnerability_alerts = self.config["vulnerabilityAlerts"]
        self.assertEqual(vulnerability_alerts["prConcurrentLimit"], 2)
        self.assertFalse(vulnerability_alerts["automerge"])
        self.assertEqual(self.config["prConcurrentLimit"], 2)
        self.assertEqual(self.config["branchConcurrentLimit"], 2)


if __name__ == "__main__":
    unittest.main()
