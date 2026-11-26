#!/usr/bin/env python3
"""Reject unsafe Bababou WAF Terraform plans without printing plan contents.

Reads `tofu show -json` from stdin; no network, Terraform state or secrets.
The only allowed operation is adding the one approved rate-limit rule to an
already imported WAF resource. No plan file or JSON is stored or printed.
"""

import json
import sys

ADDRESS = "vercel_firewall_config.bababou"
HOSTS = {"bababou.com", "www.bababou.com", "bababou.albandrieu.com"}
PROJECT = "prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0"
TEAM = "team_3vukFMXCzaUZEyGAqLAGmXaf"


class Rejected(Exception):
    """Non-sensitive error message only."""


def ensure(ok: bool, why: str) -> None:
    if not ok:
        raise Rejected(why)


def check_unknown(unknown: object) -> None:
    """Only the server-assigned ID of the new rule can be computed."""
    if not unknown:
        return
    ensure(isinstance(unknown, dict) and set(unknown) == {"rules"}, "UNKNOWN_ATTRIBUTES")
    rules = unknown["rules"]
    ensure(isinstance(rules, list) and len(rules) == 1, "UNKNOWN_ATTRIBUTES")
    node = rules[0]
    ensure(isinstance(node, dict) and set(node) == {"rule"}, "UNKNOWN_ATTRIBUTES")
    items = node["rule"]
    ensure(isinstance(items, list) and len(items) == 1, "UNKNOWN_ATTRIBUTES")
    rule = items[0]
    ensure(isinstance(rule, dict) and rule == {"id": True}, "UNKNOWN_ATTRIBUTES")


def check_rule(value: object) -> None:
    ensure(isinstance(value, list) and len(value) == 1, "INVALID_RULES_CONTAINER")
    root = value[0]
    ensure(isinstance(root, dict) and isinstance(root.get("rule"), list)
           and len(root["rule"]) == 1, "EXPECTED_ONE_RATE_RULE")
    rule = root["rule"][0]
    ensure(isinstance(rule, dict) and rule.get("active") is True,
           "RATE_RULE_NOT_ACTIVE")
    groups = rule.get("condition_group")
    ensure(isinstance(groups, list) and len(groups) == 3, "RATE_CONDITION_DRIFT")
    names = []
    for group in groups:
        ensure(isinstance(group, dict), "RATE_CONDITION_DRIFT")
        conditions = group.get("conditions")
        ensure(isinstance(conditions, list) and len(conditions) == 1, "RATE_CONDITION_DRIFT")
        c = conditions[0]
        ensure(isinstance(c, dict) and c.get("type") == "host"
               and c.get("op") == "eq" and c.get("neg") in (None, False)
               and isinstance(c.get("value"), str), "RATE_CONDITION_DRIFT")
        names.append(c["value"])
    ensure(len(set(names)) == 3 and set(names) == HOSTS, "RATE_HOSTS_DRIFT")
    action = rule.get("action")
    ensure(isinstance(action, dict) and action.get("action") == "rate_limit",
           "RATE_ACTION_DRIFT")
    ensure(action.get("action_duration") in (None, ""), "PERSISTENT_ACTION_NOT_ALLOWED")
    rate = action.get("rate_limit")
    ensure(isinstance(rate, dict) and rate.get("limit") == 300
           and rate.get("window") == 60 and rate.get("keys") == ["ip"]
           and rate.get("algo") == "fixed_window"
           and rate.get("action") == "deny", "RATE_SETTINGS_DRIFT")


def check_plan(plan: object) -> None:
    ensure(isinstance(plan, dict), "INVALID_PLAN")
    changes = plan.get("resource_changes")
    ensure(isinstance(changes, list) and len(changes) == 1, "EXPECTED_ONE_RESOURCE_CHANGE")
    change = changes[0]
    ensure(isinstance(change, dict) and change.get("address") == ADDRESS
           and change.get("type") == "vercel_firewall_config"
           and change.get("mode") == "managed", "UNEXPECTED_RESOURCE")
    detail = change.get("change")
    ensure(isinstance(detail, dict) and detail.get("actions") == ["update"],
           "MUST_UPDATE_IMPORTED_WAF")
    before, after = detail.get("before"), detail.get("after")
    ensure(isinstance(before, dict) and isinstance(after, dict), "INVALID_RESOURCE_VALUES")
    ensure(before.get("project_id") == PROJECT and after.get("project_id") == PROJECT
           and before.get("team_id") == TEAM and after.get("team_id") == TEAM,
           "WRONG_PROJECT_OR_TEAM")
    ensure(before.get("enabled") is True and after.get("enabled") is True,
           "FIREWALL_MUST_REMAIN_ENABLED")
    ensure(before.get("rules") in (None, [], [{"rule": []}]),
           "UNMANAGED_RULES_ALREADY_EXIST")

    # No other field may change, including provider-managed OWASP, anti-bot,
    # IP rules, resource ID or unknown attributes.
    all_keys = set(before) | set(after)
    for key in all_keys - {"rules"}:
        ensure(before.get(key) == after.get(key), "UNEXPECTED_WAF_CHANGE")
    ensure(not detail.get("before_sensitive") and not detail.get("after_sensitive"),
           "UNEXPECTED_SENSITIVE_ATTRIBUTES")
    check_unknown(detail.get("after_unknown"))
    check_rule(after.get("rules"))

    # Terraform can include planned outputs; refuse if they change as well.
    output_changes = plan.get("output_changes", {})
    ensure(output_changes in ({}, None), "UNEXPECTED_OUTPUT_CHANGE")
    ensure(not plan.get("resource_drift"), "OUT_OF_BAND_DRIFT")


def main() -> int:
    try:
        check_plan(json.load(sys.stdin))
    except Rejected as exc:
        print("WAF_PLAN_REJECTED: " + str(exc), file=sys.stderr)
        return 2
    except (ValueError, TypeError, OSError):
        print("WAF_PLAN_REJECTED: INVALID_JSON", file=sys.stderr)
        return 2
    print("WAF_PLAN_ALLOWED: rate-only change, one imported firewall resource")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
