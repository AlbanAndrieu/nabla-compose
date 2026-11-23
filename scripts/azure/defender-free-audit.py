#!/usr/bin/env python3
"""Read-only Microsoft Defender for Cloud pricing audit; never handles secrets.

The Microsoft.Security/pricings API uses pricingTier=Standard even for the
*free* FoundationalCspm and Discovery services. These two names alone are
accepted only when all premium Defender plans report Free.
Calls az rest GET; refuses to mutate Azure or install extensions.
The response is subscription-scope only, not a definitive billing statement.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys

EXPECTED_TENANT = "441414ec-960f-4d6a-a00c-d0d14955a7f1"
EXPECTED_SUBSCRIPTION = "6391d770-8956-47ab-8696-18ad1d52ecc5"
REST_API = "2024-01-01"
SAFE_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
FREE_BASE_COMPONENTS = frozenset({"FoundationalCspm", "Discovery"})
# All other plans are premium when Standard, including CloudPosture.


def az(*arguments: str):
    command = ["az", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40, check=False)
    if result.returncode:
        raise RuntimeError("Azure CLI command unavailable or permission denied (tokens omitted)")
    return json.loads(result.stdout)


def evaluate_pricing(records: dict) -> tuple[bool, list[dict]]:
    if not isinstance(records, dict) or not isinstance(records.get("value"), list):
        raise ValueError("Unexpected Microsoft.Security/pricings payload")
    observed = []
    for item in records["value"]:
        if not isinstance(item, dict):
            raise ValueError("Unexpected pricing entry")
        props = item.get("properties") or {}
        name, tier = item.get("name"), props.get("pricingTier")
        if not isinstance(name, str) or tier not in ("Free", "Standard"):
            raise ValueError("Unknown Microsoft.Security pricing type or tier")
        observed.append({"plan": name, "tier": tier})
    names = {p["plan"] for p in observed}
    if not {"CloudPosture", "FoundationalCspm", "Discovery"} <= names:
        raise ValueError("Incomplete Defender pricing inventory: missing posture or discovery")
    if len(names) != len(observed):
        raise ValueError("Duplicate pricing records prevent unambiguous evaluation")
    # These two specific `Standard` entries describe the FREE base CSPM
    # offering / discovery (not advanced CloudPosture). Unknown Standard
    # entries fail closed to avoid accidentally approving a paid plan.
    premium_standard = [
        p for p in observed if p["tier"] == "Standard" and p["plan"] not in FREE_BASE_COMPONENTS
    ]
    return len(premium_standard) == 0, observed


def main():
    expected_tenant = os.environ.get("ENTRA_NABLA_TENANT_ID", EXPECTED_TENANT)
    subscription = os.environ.get("AZURE_SUBSCRIPTION_ID", EXPECTED_SUBSCRIPTION)
    if not SAFE_RE.fullmatch(expected_tenant) or not SAFE_RE.fullmatch(subscription):
        print("DENIED: invalid tenant/subscription configuration", file=sys.stderr)
        return 2
    if expected_tenant.lower() != EXPECTED_TENANT or subscription.lower() != EXPECTED_SUBSCRIPTION:
        print("DENIED: tenant/subscription mismatch", file=sys.stderr)
        return 2
    try:
        account = az("account", "show", "--output", "json")
        if account.get("tenantId", "").lower() != EXPECTED_TENANT or account.get("id", "").lower() != EXPECTED_SUBSCRIPTION:
            raise ValueError("Azure CLI is not selecting the personal Nabla tenant/subscription")
        url = ("https://management.azure.com/subscriptions/" + subscription +
               "/providers/Microsoft.Security/pricings?api-version=" + REST_API)
        good, pricing = evaluate_pricing(az("rest", "--method", "get", "--url", url, "--output", "json"))
        foundational = next(p for p in pricing if p["plan"] == "FoundationalCspm")
        discovery = next(p for p in pricing if p["plan"] == "Discovery")
        premium = [p for p in pricing if p["tier"] == "Standard"
                   and p["plan"] not in FREE_BASE_COMPONENTS]
        print(json.dumps({
            "tenant_matched": True,
            "subscription_matched": True,
            "no_premium_standard_plans_at_subscription_scope": good,
            "foundational_cspm": {
                "pricing_tier": foundational["tier"],
                "enabled": foundational["tier"] == "Standard",
                "product": "FREE even when pricingTier=Standard",
            },
            "discovery": {
                "pricing_tier": discovery["tier"],
                "enabled": discovery["tier"] == "Standard",
                "product": "base discovery component, not premium CloudPosture",
            },
            "premium_standard_plans": premium,
            "plans": pricing,
            "limitations": [
                "No resource-level pricing overrides or actual invoice inspected",
                "Free Foundational CSPM is not paid Defender CSPM (CloudPosture)",
                "P30D on a Free plan is remaining optional trial, not a billing deadline",
            ],
        }, indent=2))
        return 0 if good else 3
    except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print("DENIED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
