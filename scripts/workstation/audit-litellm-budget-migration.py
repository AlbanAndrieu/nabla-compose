#!/usr/bin/env python3
"""Read-only budget migration preflight across LiteLLM proxies; no secrets printed."""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROXIES = (
    ("workstation", "http://127.0.0.1:4000", "LITELLM_MASTER_KEY"),
    ("truenas", "http://127.0.0.1:14000", "LITELLM_TRUENAS_MASTER_KEY"),
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truenas-transport", choices=("tunnel", "health-only"), default="health-only",
                        help="Tunnel uses 127.0.0.1:14000; health-only never sends credentials to TrueNAS")
    args = parser.parse_args()
    print("migration_mode=read_only")
    print("NOTE: TrueNAS admin audit requires an encrypted tunnel on localhost:14000; direct LAN port 4000 is health-only")
    print("truenas_health_url=http://172.17.0.24:4000/health/liveliness")
    for label, base, variable in PROXIES:
        if label == "truenas" and args.truenas_transport == "health-only":
            try:
                with urlopen("http://172.17.0.24:4000/health/liveliness", timeout=5) as response:
                    print(f"truenas: liveliness_http_status={response.status}")
            except (HTTPError, URLError, TimeoutError, OSError):
                print("truenas: liveliness=unavailable")
            print("truenas: admin_audit=skipped_no_encrypted_transport")
            continue
        key = os.environ.get(variable)
        if label == "truenas" and not key:
            key = os.environ.get("LITELLM_MASTER_KEY")
            if key:
                print("truenas: credential_source=workstation_master_assumed_not_verified")
        if not key:
            print(f"{label}: credential=missing (set {variable} privately)")
            continue
        request = Request(base + "/key/list", headers={"Authorization": "Bearer " + key})
        try:
            with urlopen(request, timeout=8) as response:
                data = json.load(response)
        except HTTPError as exc:
            print(f"{label}: key_list_http_status={exc.code}")
            continue
        except (URLError, TimeoutError, OSError, ValueError):
            print(f"{label}: key_list=unavailable")
            continue
        if not isinstance(data, dict):
            print(f"{label}: response=unexpected")
            continue
        # Only aggregate counts. Never print token IDs, aliases, user identifiers or spend logs.
        keys = data.get("keys")
        print(f"{label}: key_list=accessible count={len(keys) if isinstance(keys, list) else 'unresolved'}")
        print(f"{label}: budget_export=not_attempted")
    print("NOTE: this is a connectivity/authorization preflight, not a spend or budget migration")
    print("NOTE: preserve historical spend/reset state in source until verified; never copy hashed keys as live tokens")
    return 0

if __name__ == "__main__":
    sys.exit(main())
