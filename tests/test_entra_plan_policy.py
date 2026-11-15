"""Offline negative tests of the Entra CI allowlist."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "scripts/entra/check-plan.py"
SPEC = importlib.util.spec_from_file_location("entra_plan_policy", PATH)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def change(address, actions, after=None):
    return {"address": address, "type": address.split(".")[0],
            "change": {"actions": actions, "after": after or {}}}


class PlanPolicyTests(unittest.TestCase):
    def test_allows_disposable_app_create(self):
        a = 'azuread_application_registration.workload["reader"]'
        self.assertEqual(POLICY.evaluate({"resource_changes": [
            change(a, ["create"], {"display_name": "nabla-iam-lab-workload-reader"})
        ]}), (1, []))

    def test_blocks_modify_replace_delete(self):
        a = 'azuread_service_principal.workload["reader"]'
        for actions in (["update"], ["delete"], ["delete", "create"]):
            with self.subTest(actions=actions):
                self.assertTrue(POLICY.evaluate({"resource_changes": [
                    change(a, actions)
                ]})[1])

    def test_blocks_groups_and_implicit_graph_grants(self):
        app = 'azuread_application_registration.workload["reader"]'
        self.assertTrue(POLICY.evaluate({"resource_changes": [
            change('azuread_group.lab["readers"]', ["create"])
        ]})[1])
        self.assertTrue(POLICY.evaluate({"resource_changes": [
            change(app, ["create"], {
                "display_name": "nabla-iam-lab-workload-reader",
                "required_resource_access": [{"resource_app_id": "x"}]
            })
        ]})[1])

    def test_blocks_enabled_negative_principal(self):
        self.assertTrue(POLICY.evaluate({"resource_changes": [
            change('azuread_service_principal.workload["denied"]', ["create"],
                   {"account_enabled": True})
        ]})[1])


if __name__ == "__main__":
    unittest.main()
