#!/usr/bin/env python3
"""Read-only LiteLLM workstation + TrueNAS audit, no completion calls.

Never prints keys, responses, URLs with credentials, or secret-bearing errors.
Admin key metadata is queried ONLY on workstation loopback.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOCAL = os.environ.get("LITELLM_WORKSTATION_URL", "http://127.0.0.1:4000").rstrip("/")
TRUENAS = os.environ.get("LITELLM_TRUENAS_URL", "http://172.17.0.24:4000").rstrip("/")
KEYS = {
    "openclaw": "e00535fec79117191d28a7f51723b691de015306f74407b80d5a6b69b10c00af",
    "ide": "d8e5df6f6f73bd46a9042ccc94e35db56469f20335350f530fa0a24ca1821c04",
    "n8n": "921d2c2fe3d14e1ea3cc3409b6a5122845ee5896766c745a9763a2fb6f8658e9",
    "openclaw-main": "3ac174b8a4cdafe808890fbff93eaff6f405ad24dc7638fbf3ea8b492f4f610b",
}


def get(url: str, secret: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=5) as res:
            data = res.read(262144)
            try:
                obj = json.loads(data)
            except (ValueError, UnicodeError):
                obj = {}
            return res.status, obj if isinstance(obj, dict) else {}
    except HTTPError as err:
        return err.code, {}
    except (URLError, TimeoutError, OSError, ValueError):
        return 0, {}


def report(name: str, base: str) -> None:
    print(f"proxy={name}")
    for endpoint in ("/health/liveliness", "/health/readiness"):
        code, _ = get(base + endpoint)
        print(f"  {endpoint.strip('/').replace('/', '_')}_http={code or 'unreachable'}")


def audit() -> None:
    report("workstation", LOCAL)
    report("truenas", TRUENAS)
    # Never transmit workstation master key outside explicitly configured loopback.
    if LOCAL not in ("http://127.0.0.1:4000", "http://localhost:4000", "http://[::1]:4000"):
        print("admin_audit=skipped_non_loopback_workstation_url")
        return
    master = os.environ.get("LITELLM_MASTER_KEY")
    if not master:
        print("admin_audit=skipped_master_key_not_in_environment")
        print("NOTE: key IDs alone do not authorize administrative queries")
        return
    for name, key_id in KEYS.items():
        code, data = get(LOCAL + "/key/info?" + urlencode({"key": key_id}), master)
        print(f"key={name} http={code or 'unreachable'}")
        if code != 200:
            continue
        info = data.get("info")
        if not isinstance(info, dict):
            print("  metadata=unavailable")
            continue
        for field in ("spend", "max_budget", "tpm_limit", "rpm_limit", "budget_duration", "budget_reset_at"):
            value = info.get(field)
            if type(value) in (int, float) or (field in ("budget_duration", "budget_reset_at") and isinstance(value, str)):
                print(f"  {field}={value}")
            else:
                print(f"  {field}=not_reported")
        spend, budget = info.get("spend"), info.get("max_budget")
        if (
            type(spend) in (int, float)
            and type(budget) in (int, float)
            and 0 < budget < float("inf")
            and 0 <= spend < float("inf")
        ):
            print(f"  budget_usage_pct={100 * spend / budget:.1f}")
            print(f"  budget_remaining={max(0.0, budget - spend):.4f}")
        else:
            print("  budget_usage_pct=not_reported")
        print("  NOTE: limits may also apply at team/model/upstream level")
    print("NOTE: TPM means tokens per minute; a 200000 TPM quota is not a monetary budget")
    print("NOTE: this is read-only; no chat, embedding, key creation or spend reset")


if __name__ == "__main__":
    audit()
