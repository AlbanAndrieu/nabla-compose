#!/usr/bin/env python3
"""Fail-closed, read-only Vercel WAF baseline/acceptance check.

Never emits payloads, rule names, credentials, IPs, paths, or URLs. The JSON
may contain request metadata: supply it through stdin or a private file only.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TEAM = "team_3vukFMXCzaUZEyGAqLAGmXaf"
# site -> (Vercel project, hosts of its one rate-limit rule; None while it has no rule)
SITES = {
    "bababou": ("prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0",
                {"bababou.com", "www.bababou.com", "bababou.albandrieu.com"}),
    "alban": ("prj_x6leAdsVXdHRcoG1zsSiy5pngEYa", None),
}
OWASP = {"sd", "gen", "sf", "java", "ma", "rfi", "rce", "php", "xss", "lfi", "sqli"}
BLOCK = {"rce", "xss", "sqli"}


class PolicyViolation(Exception):
    """Non-sensitive machine-readable check failure."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PolicyViolation(code)


def evaluate(payload: dict, phase: str, site: str = "bababou") -> None:
    """Check the entire scoped active WAF, not only changes intended by IaC."""
    require(phase in {"baseline", "rate-only", "enforced"}, "INVALID_PHASE")
    require(site in SITES, "UNKNOWN_SITE")
    project, expected_hosts = SITES[site]
    require(phase == "baseline" or expected_hosts is not None, "NO_RATE_RULE_FOR_SITE")
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    require(isinstance(payload, dict), "INVALID_PAYLOAD")
    require(payload.get("projectKey") == project + "#active", "WRONG_PROJECT_OR_VERSION")
    require(payload.get("ownerId") == TEAM, "WRONG_TEAM")
    require(payload.get("firewallEnabled") is True, "FIREWALL_DISABLED")

    managed = payload.get("managedRules")
    require(isinstance(managed, dict), "MISSING_MANAGED_RULES")
    require(set(managed) == {"bot_protection"}, "UNEXPECTED_MANAGED_RULESET")
    bot = managed["bot_protection"]
    require(isinstance(bot, dict) and bot.get("active") is True and bot.get("action") == "challenge", "BOT_PROTECTION_DRIFT")

    crs = payload.get("crs")
    require(isinstance(crs, dict), "MISSING_OWASP_RULES")
    require(set(crs) == OWASP, "OWASP_INVENTORY_DRIFT")
    for name in sorted(OWASP):
        rule = crs[name]
        require(isinstance(rule, dict), "INVALID_OWASP_RULE")
        expected_action = "deny" if phase == "enforced" and name in BLOCK else "log"
        expected_active = name in (BLOCK | {"gen"})
        require(rule.get("action") == expected_action and rule.get("active") is expected_active,
                "OWASP_" + name.upper() + "_DRIFT")

    require(payload.get("ips") == [], "UNMANAGED_IP_RULES")
    rules = payload.get("rules")
    require(isinstance(rules, list), "MISSING_CUSTOM_RULES")
    if phase == "baseline":
        require(rules == [], "BASELINE_HAS_CUSTOM_RULES")
        return

    require(len(rules) == 1, "EXPECTED_ONE_RATE_RULE")
    rule = rules[0]
    require(isinstance(rule, dict) and rule.get("active") is True, "RATE_RULE_INACTIVE")
    groups = rule.get("conditionGroup")
    require(isinstance(groups, list) and len(groups) == len(expected_hosts), "RATE_SCOPE_DRIFT")
    hosts = []
    for group in groups:
        conditions = group.get("conditions") if isinstance(group, dict) else None
        require(isinstance(conditions, list) and len(conditions) == 1, "RATE_CONDITION_DRIFT")
        condition = conditions[0]
        require(isinstance(condition, dict) and condition.get("type") == "host" and
                condition.get("op") == "eq" and condition.get("neg") in (None, False) and
                isinstance(condition.get("value"), str), "RATE_CONDITION_DRIFT")
        hosts.append(condition["value"])
    require(len(set(hosts)) == len(hosts) and set(hosts) == expected_hosts, "RATE_HOSTS_DRIFT")
    action = rule.get("action", {})
    mitigation = action.get("mitigate", {}) if isinstance(action, dict) else {}
    require(isinstance(mitigation, dict), "RATE_ACTION_DRIFT")
    require(mitigation.get("action") == "rate_limit", "RATE_ACTION_DRIFT")
    require(mitigation.get("actionDuration") in (None, ""), "PERSISTENT_ACTION_UNEXPECTED")
    rate = mitigation.get("rateLimit")
    require(isinstance(rate, dict), "MISSING_RATE_POLICY")
    require(rate.get("limit") == 300 and rate.get("window") == 60 and
            rate.get("keys") == ["ip"] and rate.get("algo") == "fixed_window" and
            rate.get("action") == "deny", "RATE_POLICY_DRIFT")


def read_live(project: str) -> dict:
    token = os.environ.get("VERCEL_API_TOKEN", "")
    require(bool(token.strip()), "MISSING_VERCEL_API_TOKEN")
    query = urlencode({"projectId": project, "teamId": TEAM})
    req = Request("https://api.vercel.com/v1/security/firewall/config/active?" + query,
                  headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    # No request payloads are printed even in case of HTTP/network errors.
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("baseline", "rate-only", "enforced"), required=True)
    parser.add_argument("--site", choices=sorted(SITES), default="bababou")
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--live", action="store_true", help="Vercel GET, never changes rules")
    sources.add_argument("--file", type=Path, help="Private Vercel API JSON snapshot")
    sources.add_argument("--stdin", action="store_true", help="Read JSON via stdin")
    args = parser.parse_args(argv)
    try:
        if args.live:
            payload = read_live(SITES[args.site][0])
        elif args.stdin:
            payload = json.load(sys.stdin)
        else:
            with args.file.open(encoding="utf-8") as source:
                payload = json.load(source)
        evaluate(payload, args.phase, args.site)
    except PolicyViolation as exc:
        print("WAF_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print("WAF_PREFLIGHT_FAIL: READ_OR_PARSE_ERROR", file=sys.stderr)
        return 2
    print("WAF_PREFLIGHT_PASS: " + args.site + " " + args.phase + " (read-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
