#!/usr/bin/env python3
"""Bootstrap one named LiteLLM TrueNAS admin via SSH tunnel; never disable bootstrap login."""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:14000"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Personal email for the named administrator")
    parser.add_argument("--apply", action="store_true", help="Create account without password; default is dry-run")
    parser.add_argument("--inspect-existing", action="store_true", help="Read-only check via /user/info over SSH tunnel")
    args = parser.parse_args()
    email = args.email.strip()
    if not email or "@" not in email or any(c.isspace() for c in email):
        parser.error("--email must be a valid-looking email address")
    if not args.apply and not args.inspect_existing:
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
    if args.inspect_existing:
        from urllib.parse import urlencode
        request = Request(BASE + "/user/info?" + urlencode({"user_id": email}),
                          headers={"Authorization": "Bearer " + key})
        try:
            with urlopen(request, timeout=15) as response:
                data = json.load(response)
            print("user_lookup_http_status=200")
            if isinstance(data, dict):
                user = data.get("user_info", data)
                if isinstance(user, dict):
                    print("user_role=" + str(user.get("user_role", "unresolved")))
                    print("user_record_present=true")
        except HTTPError as exc:
            print(f"user_lookup_http_status={exc.code} (response body suppressed)")
            return 1
        except (URLError, OSError, TimeoutError, ValueError):
            print("ERROR: user lookup unavailable or unexpected response", file=sys.stderr)
            return 1
        return 0
    # LiteLLM /user/new rejects password (422). Password setup uses an invitation.
    payload = json.dumps({
        "user_email": email,
        "user_role": "proxy_admin",
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
        if exc.code == 409:
            print("NEXT: run --inspect-existing to check the existing account; do not recreate blindly", file=sys.stderr)
        return 1
    except (URLError, OSError, TimeoutError):
        print("ERROR: SSH tunnel or proxy unavailable", file=sys.stderr)
        return 1
    print("NOTE: verify fresh private-window login with named account and permissions")
    print("NEXT: create an invitation in LiteLLM UI > Internal Users > Invite User")
    print("NEXT: follow the invitation link privately to set a unique password")
    print("NOTE: bootstrap UI login remains enabled until named admin login is verified")
    print("NOTE: do NOT enable disable_env_credential_login before independent login succeeds")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
