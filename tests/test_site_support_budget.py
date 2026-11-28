"""Static and pure policy tests for budget isolation, no network or secrets."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-site-support-budget.py"
spec = importlib.util.spec_from_file_location("site_support_budget_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BudgetTests(unittest.TestCase):
    def test_scoped_budget_and_header_wiring(self):
        value = module.policy_check()
        self.assertEqual(value["endUserId"], "site-support@albandrieu.com")
        self.assertEqual(value["budgetUsd"], 3)
        self.assertEqual(value["duration"], "30d")

    def test_no_claim_when_missing_or_mismatch(self):
        p = module.policy_check()
        self.assertFalse(module.matches(None, p))
        self.assertFalse(module.matches({"end_user_id":p["endUserId"],"max_budget":10,"budget_duration":"30d"},p))
        self.assertTrue(module.matches({"end_user_id":p["endUserId"],"max_budget":3,"budget_duration":"30d"},p))

    def test_no_mutation_on_check(self):
        from unittest.mock import patch
        with patch.object(module.lib, "request") as remote:
            self.assertEqual(module.main(["--check"]), 0)
            remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
