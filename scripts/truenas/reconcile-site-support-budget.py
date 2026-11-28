#!/usr/bin/env python3
"""Read-only by default: verify a USD budget dedicated to OpenWebUI site-support.

The OpenWebUI v0.11 account site-support@albandrieu.com sends
X-OpenWebUI-User-Email; LiteLLM config maps it to customer/end_user.
Apply only creates a missing customer, never overwrites an existing budget.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/litellm/site-support-budget.json"
CONFIG = ROOT / "apps/litellm/config.yaml"
WEBUI = ROOT / "apps/openwebui/compose.yml"
LIB_PATH = Path(__file__).with_name("provision-openclaw-litellm-keys.py")
spec = importlib.util.spec_from_file_location("site_support_litellm_lib", LIB_PATH)
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


def policy_check() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    litellm = CONFIG.read_text(encoding="utf-8")
    openwebui = WEBUI.read_text(encoding="utf-8")
    if "ENABLE_FORWARD_USER_INFO_HEADERS=true" not in openwebui:
        raise ValueError("OpenWebUI identity forwarding disabled")
    if ("header_name: X-OpenWebUI-User-Email" not in litellm
            or "litellm_user_role: customer" not in litellm):
        raise ValueError("LiteLLM customer identity mapping absent")
    if not (policy["endUserId"] == "site-support@albandrieu.com"
            and policy["budgetUsd"] > 0
            and policy["budgetUsd"] <= 3
            and policy["duration"] == "30d"):
        raise ValueError("Unexpected site-support budget policy")
    return policy


def query(master: str, end_user_id: str) -> tuple[int, object]:
    return lib.request("/customer/info?" + urllib.parse.urlencode(
        {"end_user_id": end_user_id}), master)


def matches(payload: object, policy: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    info = payload.get("info", payload)
    if not isinstance(info, dict):
        return False
    return (info.get("end_user_id", info.get("user_id")) == policy["endUserId"]
            and info.get("max_budget") == policy["budgetUsd"]
            and info.get("budget_duration") == policy["duration"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="offline code policy only")
    parser.add_argument("--apply", action="store_true", help="create a missing budget")
    args = parser.parse_args(argv)
    policy = policy_check()
    if args.check:
        print("site_support_budget=CODED; amount_usd=3; duration=30d; runtime=NOT_VERIFIED")
        return 0
    master = (lib.container_environment() or {}).get("LITELLM_MASTER_KEY")
    if not master:
        print("site_support_budget=UNVERIFIED; reason=master_unavailable")
        return 2
    status, record = query(master, policy["endUserId"])
    if status == 200:
        valid = matches(record, policy)
        print("site_support_budget=" + ("VERIFIED" if valid else "MISMATCH"))
        return 0 if valid else 2
    if status != 404 or not args.apply:
        print("site_support_budget=" + ("MISSING" if status == 404 else "UNVERIFIED"))
        return 2
    created, _ = lib.request("/customer/new", master, {
        "end_user_id": policy["endUserId"],
        "max_budget": policy["budgetUsd"],
        "budget_duration": policy["duration"],
    })
    if created not in (200, 201):
        print("site_support_budget=CREATE_FAILED")
        return 2
    status, record = query(master, policy["endUserId"])
    valid = status == 200 and matches(record, policy)
    print("site_support_budget=" + ("VERIFIED" if valid else "UNVERIFIED"))
    return 0 if valid else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as exc:
        print("site_support_budget=INVALID_POLICY; " + type(exc).__name__)
        sys.exit(2)
