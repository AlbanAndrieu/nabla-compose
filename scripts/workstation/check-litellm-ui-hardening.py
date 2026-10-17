#!/usr/bin/env python3
"""Read-only LiteLLM UI hardening checks; never send administrator credentials over LAN."""
import argparse
import pathlib
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "apps/litellm/config.yaml"
PUBLIC = "https://litellm.albandrieu.com/ui/"
LOCAL = "http://127.0.0.1:14000/health/liveliness"
LOCAL_UI = "http://127.0.0.1:14000/ui/"

def check_config():
    data = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"(?m)^general_settings:\s*$([\s\S]*?)(?=^[^\s#][^\n]*:\s*$|\Z)", data)
    if not match:
        print("config_general_settings=missing")
        return False
    lines = re.findall(r"(?m)^\s*disable_env_credential_login:\s*(\S+)\s*(?:#.*)?$", match.group(1))
    ok = lines == ["true"]
    print("config_disable_env_credential_login=" + ("true" if ok else "missing_or_invalid"))
    return ok

def public_probe():
    # No redirects: a Cloudflare Access login redirect is evidence of a challenge,
    # not proof of complete coverage or MFA policy.
    from urllib.request import build_opener, HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    request = Request(PUBLIC, headers={"User-Agent": "nabla-litellm-ui-audit/1.0"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            status, headers = response.status, response.headers
    except HTTPError as exc:
        status, headers = exc.code, exc.headers
    except (URLError, TimeoutError, OSError):
        print("public_ui=unreachable")
        return
    location = headers.get("Location", "")
    access_redirect = status in (301, 302, 303, 307, 308) and (
        "/cdn-cgi/access/" in location or "cloudflareaccess.com" in location
    )
    print("public_ui_http_status=" + str(status))
    print("public_ui_access_challenge=" + ("observed" if access_redirect else "not_observed"))
    print("NOTE: one unauthenticated probe cannot verify all routes, policy scope or MFA")

def unauthenticated_tunnel_ui_probe():
    """Report live UI response without credentials; not proof login mode is disabled."""
    from urllib.request import build_opener, HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        with build_opener(NoRedirect()).open(Request(LOCAL_UI), timeout=5) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
    except (URLError, OSError, TimeoutError):
        print("truenas_tunnel_ui=unavailable")
        return
    print(f"truenas_tunnel_ui_http_status={status}")
    print("NOTE: an unauthenticated UI response does not prove environment login is disabled")

def local_probe():
    try:
        with urlopen(LOCAL, timeout=5) as response:
            print("truenas_tunnel_liveliness_http_status=" + str(response.status))
    except (HTTPError, URLError, TimeoutError, OSError):
        print("truenas_tunnel_liveliness=unavailable")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-public", action="store_true", help="Unauthenticated HTTPS UI request, no redirects")
    parser.add_argument("--probe-tunnel", action="store_true", help="Health request to local SSH tunnel only")
    parser.add_argument("--probe-tunnel-ui", action="store_true", help="Unauthenticated UI request through SSH tunnel; no credentials sent")
    args = parser.parse_args()
    ok = check_config()
    if args.probe_public:
        public_probe()
    if args.probe_tunnel:
        local_probe()
    if args.probe_tunnel_ui:
        unauthenticated_tunnel_ui_probe()
    print("runtime_setting=not_verified (requires manual old-login rejection test)")
    print("named_admin_login=manual_acceptance_required")
    print("legacy_env_login_rejection=manual_acceptance_required")
    print("migration_or_deployment=not_performed")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
