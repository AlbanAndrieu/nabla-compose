#!/usr/bin/env python3
"""Read-only OpenClaw auth status; display counts, never profile IDs or secrets."""
import argparse
import json
import subprocess
import sys


def classify(value):
    if not isinstance(value, dict):
        return "other"
    reasons = " ".join(str(value.get(name, "")).lower()
                       for name in ("reason", "status", "cause", "code", "type"))
    if "rate" in reasons or "cooldown" in reasons or "429" in reasons:
        return "rate_cooldown"
    if any(word in reasons for word in ("billing", "quota", "credit", "disabled")):
        return "billing_or_disabled"
    return "other"


def summarize(payload):
    if not isinstance(payload, dict):
        return None
    auth = payload.get("auth")
    if not isinstance(auth, dict):
        return None
    unusable = auth.get("unusableProfiles")
    if isinstance(unusable, dict):
        entries = []
        for item in unusable.values():
            if isinstance(item, list):
                entries.extend(item[:100])
            elif isinstance(item, dict):
                entries.append(item)
    elif isinstance(unusable, list):
        entries = unusable[:100]
    else:
        return None
    categories = {"rate_cooldown": 0, "billing_or_disabled": 0, "other": 0}
    for item in entries[:100]:
        categories[classify(item)] += 1
    return categories


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        process = subprocess.run(
            ["openclaw", "models", "status", "--json"],
            capture_output=True, timeout=18, check=False)
    except (OSError, subprocess.TimeoutExpired):
        print("openclaw_model_auth_status=unavailable")
        return 2
    if process.returncode != 0 or len(process.stdout) > 1024 * 1024:
        print("openclaw_model_auth_status=unavailable")
        return 2
    try:
        data = json.loads(process.stdout)
    except (ValueError, UnicodeError):
        print("openclaw_model_auth_status=unverified")
        return 2
    categories = summarize(data)
    if categories is None:
        print("openclaw_model_auth_status=unrecognized_schema")
        return 2
    print("openclaw_model_auth_status=read_only")
    print("openclaw_unusable_rate_cooldown_count=" + str(categories["rate_cooldown"]))
    print("openclaw_unusable_billing_count=" + str(categories["billing_or_disabled"]))
    print("openclaw_unusable_other_count=" + str(categories["other"]))
    print("openclaw_session_pins=not_inspected")
    print("model_probe_sent=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
