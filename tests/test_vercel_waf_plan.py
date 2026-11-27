"""No-network negative tests for the WAF plan approval guard."""
import copy
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/security/check_vercel_waf_plan.py"
spec = importlib.util.spec_from_file_location("waf_plan", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def sample():
    before = {
        "project_id": guard.PROJECT,
        "team_id": guard.TEAM,
        "enabled": True,
        "id": guard.TEAM + "/" + guard.PROJECT,
        "managed_rulesets": [{
            "owasp": [{"gen": {"action": "log", "active": True},
                       "xss": {"action": "log", "active": True}}],
            "bot_protection": [{"active": True, "action": "challenge"}],
        }],
        "ip_rules": [],
        "rules": [],
    }
    after = copy.deepcopy(before)
    after["rules"] = [{
        "rule": [{
            "name": "Bababou public traffic rate limit",
            "active": True,
            "condition_group": [
                {"conditions": [{"type": "host", "op": "eq", "value": host}]}
                for host in sorted(guard.HOSTS)
            ],
            "action": {
                "action": "rate_limit",
                "action_duration": None,
                "rate_limit": {
                    "limit": 300, "window": 60, "keys": ["ip"],
                    "algo": "fixed_window", "action": "deny",
                },
            },
        }],
    }]
    return {"resource_changes": [{
        "address": guard.ADDRESS, "type": "vercel_firewall_config",
        "mode": "managed",
        "change": {
            "actions": ["update"], "before": before, "after": after,
            "after_unknown": {"rules": [{"rule": [{"id": True}]}]},
        },
    }]}


class WafPlanGuardTests(unittest.TestCase):
    def test_approved_rate_only_plan(self):
        guard.check_plan(sample())

    def test_create_instead_of_import_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["actions"] = ["create"]
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_destroy_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_second_resource_rejected(self):
        p = sample()
        p["resource_changes"].append(copy.deepcopy(p["resource_changes"][0]))
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_managed_owasp_change_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["managed_rulesets"][0]["owasp"][0]["xss"]["action"] = "deny"
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_bot_challenge_change_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["managed_rulesets"][0]["bot_protection"][0]["action"] = "log"
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_extra_existing_rule_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["before"]["rules"] = [{"rule": [{"name": "other"}]}]
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_wrong_hostname_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["rules"][0]["rule"][0]["condition_group"][0]["conditions"][0]["value"] = "preview.vercel.app"
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_broader_limit_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["rules"][0]["rule"][0]["action"]["rate_limit"]["limit"] = 50
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_persistent_action_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["rules"][0]["rule"][0]["action"]["action_duration"] = "1m"
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_unknown_other_than_rule_id_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after_unknown"]["managed_rulesets"] = True
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_unexpected_output_change_rejected(self):
        p = sample()
        p["output_changes"] = {"token": {"actions": ["create"]}}
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_unexpected_drift_rejected(self):
        p = sample()
        p["resource_drift"] = [{"address": guard.ADDRESS}]
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def test_wrong_project_rejected(self):
        p = sample()
        p["resource_changes"][0]["change"]["after"]["project_id"] = "other"
        self.assertRaises(guard.Rejected, guard.check_plan, p)

    def alban_import(self, actions):
        state = {"project_id": "prj_x6leAdsVXdHRcoG1zsSiy5pngEYa", "team_id": guard.TEAM}
        return {"address": "vercel_firewall_config.alban", "type": "vercel_firewall_config",
                "mode": "managed", "change": {"actions": actions, "before": state,
                                              "after": state, "importing": {"id": "x"}}}

    def test_unchanged_alban_import_ignored(self):
        p = sample()
        p["resource_changes"].append(self.alban_import(["no-op"]))
        guard.check_plan(p)

    def test_alban_import_with_changes_rejected(self):
        p = sample()
        p["resource_changes"].append(self.alban_import(["update"]))
        self.assertRaises(guard.Rejected, guard.check_plan, p)


if __name__ == "__main__":
    unittest.main()
