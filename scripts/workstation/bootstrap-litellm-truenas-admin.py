#!/usr/bin/env python3
"""Bootstrap one named LiteLLM TrueNAS admin via SSH tunnel; never disable bootstrap login."""
import argparse
import getpass
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:14000"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Personal email for the named administrator")
    parser.add_argument("--apply", action="store_true", help="Create account; default is dry-run")
    args = parser.parse_args()
    email = args.email.strip()
    if not email or "@" not in email or any(c.isspace() for c in email):
        parser.error("--email must be a valid-looking email address")
    if not args.apply:
        print("mode=dry_run")
        print("target=truenas_via_local_ssh_tunnel")
        print("role=proxy_admin")
        print("auto_create_key=false")
        print("action=POST /user/new (only with --apply)")
        print("NOTE: environment-credential login will NOT be disabled")
        return 0
    key = os.environ.get("LITELLM_TRUENAS_MASTER_KEY") or os.environ.get("LITELLM_MASTER_KEY")
    if not key:
        print("ERROR: admin credential missing from environment", file=sys.stderr)
        return 2
    # A named admin requires an independent password; avoid passing it via CLI or env.
    password = getpass.getpass("New named admin password (hidden): ")
    confirm = getpass.getpass("Confirm password (hidden): ")
    if password != confirm or len(password) < 16:
        print("ERROR: passwords mismatch or shorter than 16 characters", file=sys.stderr)
        return 2
    payload = json.dumps({
        "user_email": email,
        "user_role": "proxy_admin",
        "password": password,
        "auto_create_key": False,
    }).encode("utf-8")
    request = Request(BASE + "/user/new", data=payload, method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            # Deliberately do not print the response: it may contain generated tokens.
            response.read()
            print(f"admin_create_http_status={response.status}")
    except HTTPError as exc:
        print(f"ERROR: admin_create_http_status={exc.code} (response body suppressed)", file=sys.stderr)
        return 1
    except (URLError, OSError, TimeoutError):
        print("ERROR: SSH tunnel or proxy unavailable", file=sys.stderr)
        return 1
    finally:
        password = confirm = ""
    print("NOTE: verify fresh private-window login with named account and permissions")
    print("NOTE: password reset may be required on first login; bootstrap UI login remains enabled")
    print("NOTE: do NOT enable disable_env_credential_login before independent login succeeds")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
