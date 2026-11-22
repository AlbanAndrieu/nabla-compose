#!/usr/bin/env python3
"""Read-only Microsoft Defender for Cloud pricing audit; never handles secrets.

This is a strict guardrail, NOT proof of Foundational CSPM opt-in.
Calls az rest GET; refuses to mutate Azure or install extensions.
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
    if not any(p["plan"] == "CloudPosture" for p in observed):
        raise ValueError("CloudPosture plan not returned; cannot assert posture")
    return all(p["tier"] == "Free" for p in observed), observed


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
        print(json.dumps({"tenant_matched": True, "subscription_matched": True,
                          "no_paid_defender_plan": good, "plans": pricing,
                          "foundational_cspm_opt_in": "NOT_VERIFIED_BY_PRICINGS_API"}, indent=2))
        return 0 if good else 3
    except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print("DENIED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
