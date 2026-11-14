#!/usr/bin/env python3
"""Fail closed on dangerous plan changes; never print plan/state contents."""
import json
from pathlib import Path
import sys

ALLOWED = {
    "terraform_data.personal_tenant_guard",
    'azuread_application_registration.workload["reader"]',
    'azuread_application_registration.workload["denied"]',
    'azuread_service_principal.workload["reader"]',
    'azuread_service_principal.workload["denied"]',
}


def evaluate(plan):
    errors = []
    count = 0
    for item in plan.get("resource_changes", []):
        address = item.get("address", "")
        change = item.get("change", {})
        actions = change.get("actions", [])
        if actions == ["no-op"]:
            continue
        if actions != ["create"]:
            errors.append("Non-create operation blocked: " + address)
            continue
        if address not in ALLOWED:
            errors.append("Resource outside allowlist: " + address)
            continue
        after = change.get("after") or {}
        if item.get("type") == "azuread_application_registration":
            name = after.get("display_name", "")
            if not isinstance(name, str) or not name.startswith("nabla-iam-lab-workload-"):
                errors.append("Application outside disposable namespace")
            if after.get("required_resource_access") not in (None, []):
                errors.append("Graph API permission grant blocked")
        if address.endswith('workload["denied"]') and item.get("type") == "azuread_service_principal":
            if after.get("account_enabled") is not False:
                errors.append("Disabled test principal must remain disabled")
        count += 1
    return count, errors


def main():
    if len(sys.argv) != 2:
        return 2
    try:
        plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        if not isinstance(plan, dict) or not isinstance(plan.get("resource_changes"), list):
            raise ValueError("Invalid plan schema")
    except (OSError, ValueError):
        print("ENTRA_PLAN_DENIED: invalid private JSON", file=sys.stderr)
        return 2
    count, errors = evaluate(plan)
    if errors:
        print("ENTRA_PLAN_DENIED: " + "; ".join(errors), file=sys.stderr)
        return 2
    print("ENTRA_PLAN_OK: " + str(count) + " creates; no updates/deletes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
