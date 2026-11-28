"""No network; reject unexpected WAF drift before import and after apply."""
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/security/check_vercel_waf.py"
spec = importlib.util.spec_from_file_location("check_vercel_waf", SCRIPT)
waf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(waf)


def baseline():
    names = waf.OWASP
    return {
        "projectKey": waf.SITES["bababou"][0] + "#active",
        "ownerId": waf.TEAM,
        "firewallEnabled": True,
        "managedRules": {"bot_protection": {"action": "challenge", "active": True}},
        "crs": {name: {"active": name in (waf.BLOCK | {"gen"}), "action": "log"}
                for name in names},
        "ips": [],
        "rules": [],
    }


def enforced():
    data = baseline()
    for name in waf.BLOCK:
        data["crs"][name]["action"] = "deny"
    data["rules"].append({
        "active": True,
        "conditionGroup": [{"conditions": [{"type": "host", "op": "eq", "value": host}]}
                           for host in sorted(waf.SITES["bababou"][1])],
        "action": {"mitigate": {
            "action": "rate_limit",
            "rateLimit": {"limit": 300, "window": 60, "keys": ["ip"],
                          "algo": "fixed_window", "action": "deny"},
        }},
    })
    return data


class WafPreflightTests(unittest.TestCase):
    def passes(self, data, phase):
        self.assertIsNone(waf.evaluate(data, phase))

    def fails(self, data, phase):
        with self.assertRaises(waf.PolicyViolation):
            waf.evaluate(data, phase)

    def test_expected_baseline(self):
        self.passes(baseline(), "baseline")

    def test_expected_rate_only(self):
        data = enforced()
        for name in waf.BLOCK:
            data["crs"][name]["action"] = "log"
        self.passes(data, "rate-only")

    def test_rate_only_rejects_fake_owasp_enforcement(self):
        self.fails(enforced(), "rate-only")

    def test_expected_post_apply(self):
        self.passes(enforced(), "enforced")

    def test_tool_result_wrapper(self):
        self.passes({"result": baseline()}, "baseline")

    def test_wrong_project(self):
        data = baseline()
        data["projectKey"] = "other#active"
        self.fails(data, "baseline")

    def test_wrong_team(self):
        data = baseline()
        data["ownerId"] = "other"
        self.fails(data, "baseline")

    def test_bot_challenge_disabled(self):
        data = baseline()
        data["managedRules"]["bot_protection"]["action"] = "log"
        self.fails(data, "baseline")

    def test_extra_managed_ruleset(self):
        data = baseline()
        data["managedRules"]["ai_bots"] = {"action": "deny", "active": True}
        self.fails(data, "baseline")

    def test_owasp_bypass(self):
        data = enforced()
        data["crs"]["xss"]["action"] = "log"
        self.fails(data, "enforced")

    def test_unknown_owasp_group(self):
        data = baseline()
        data["crs"]["new_group"] = {"active": True, "action": "deny"}
        self.fails(data, "baseline")

    def test_custom_rule_drift(self):
        data = baseline()
        data["rules"] = [{"name": "unmanaged"}]
        self.fails(data, "baseline")

    def test_hostname_scope_drift(self):
        data = enforced()
        data["rules"][0]["conditionGroup"][0]["conditions"][0]["value"] = "preview.vercel.app"
        self.fails(data, "enforced")

    def test_rate_threshold_drift(self):
        data = enforced()
        data["rules"][0]["action"]["mitigate"]["rateLimit"]["limit"] = 500
        self.fails(data, "enforced")

    def test_unexpected_persistent_action(self):
        data = enforced()
        data["rules"][0]["action"]["mitigate"]["actionDuration"] = "1m"
        self.fails(data, "enforced")

    def test_malformed_mitigation(self):
        data = enforced()
        data["rules"][0]["action"]["mitigate"] = None
        self.fails(data, "rate-only")

    def test_extra_condition_drift(self):
        data = enforced()
        data["rules"][0]["conditionGroup"][0]["conditions"].append({"type": "path", "op": "eq", "value": "/api"})
        self.fails(data, "enforced")

    def test_parse_from_json_bytes(self):
        self.passes(json.loads(json.dumps(enforced())), "enforced")

    def test_alban_baseline(self):
        data = baseline()
        data["projectKey"] = waf.SITES["alban"][0] + "#active"
        self.assertIsNone(waf.evaluate(data, "baseline", "alban"))
        with self.assertRaises(waf.PolicyViolation):
            waf.evaluate(data, "baseline")  # Bababou's project is not Alban's

    def test_alban_has_no_rate_rule_yet(self):
        data = enforced()
        data["projectKey"] = waf.SITES["alban"][0] + "#active"
        for phase in ("rate-only", "enforced"):
            with self.assertRaises(waf.PolicyViolation):
                waf.evaluate(data, phase, "alban")


if __name__ == "__main__":
    unittest.main()
