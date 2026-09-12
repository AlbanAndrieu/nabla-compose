#!/usr/bin/env python3
"""Read-only Cloudflare API and Access diagnostics without printing credentials.

Run on a workstation/TrueNAS host with CLOUDFLARE_ACCOUNT_ID and
CLOUDFLARE_API_TOKEN exported, or execute through stdin inside the FastAPI
container so the exact runtime environment is tested:

    docker exec -i fastapi-sample python - < scripts/cloudflare/diagnose-cloudflare-api.py

Optionally test a protected homelab URL with the configured Access Service Token:

    python scripts/cloudflare/diagnose-cloudflare-api.py \
      --access-url https://2fauth.albandrieu.com/

The Access test only sends CF_ACCESS_CLIENT_ID/CF_ACCESS_CLIENT_SECRET to an
HTTPS hostname in the owned albandrieu.com zone.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

API_BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT_SECONDS = 6.0
_DEFAULT_DENY_FRAGMENT = "this resource is blocked by this account's default-deny policy"


def env_state(name: str) -> tuple[bool, int]:
    value = os.getenv(name, "").strip()
    return bool(value), len(value)


def resolvers() -> list[str]:
    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    values: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("nameserver "):
            continue
        value = line.split(None, 1)[1].strip()
        if value and value not in values:
            values.append(value)
    return values


def safe_payload(raw: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def summarize_payload(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "non-JSON response"
    parts: list[str] = []
    if "success" in payload:
        parts.append(f"success={payload.get('success')}")
    result = payload.get("result")
    if isinstance(result, list):
        parts.append(f"result_count={len(result)}")
    elif isinstance(result, dict):
        status = result.get("status")
        if status:
            parts.append(f"status={status}")
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        code = first.get("code")
        message = str(first.get("message") or "").strip().replace("\n", " ")[:240]
        if code is not None:
            parts.append(f"error_code={code}")
        if message:
            parts.append(f"error={message}")
    return " · ".join(parts) or "response parsed"


def api_get(label: str, path: str, token: str) -> tuple[int | None, dict[str, Any] | None]:
    request = Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "nabla-compose-cloudflare-diagnostic/2",
        },
        method="GET",
    )
    started = time.monotonic()
    status: int | None = None
    payload: dict[str, Any] | None = None
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS provider endpoint
            status = int(response.status)
            payload = safe_payload(response.read(512 * 1024))
    except HTTPError as exc:
        status = int(exc.code)
        payload = safe_payload(exc.read(512 * 1024))
    except (URLError, TimeoutError, OSError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        print(f"❌ {label}: transport_error={type(exc).__name__} · {elapsed_ms}ms · {str(exc)[:240]}")
        return None, None

    elapsed_ms = round((time.monotonic() - started) * 1000)
    icon = "✅" if status is not None and 200 <= status < 300 else "❌"
    print(f"{icon} {label}: HTTP {status} · {elapsed_ms}ms · {summarize_payload(payload)}")
    return status, payload


def token_active(status: int | None, payload: dict[str, Any] | None) -> bool:
    return bool(
        status == 200
        and isinstance(payload, dict)
        and isinstance(payload.get("result"), dict)
        and payload["result"].get("status") == "active"
    )


def access_url_allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and bool(
        host and (host == "albandrieu.com" or host.endswith(".albandrieu.com"))
    )


def access_response_evidence(status: int, headers: Any, body: bytes) -> tuple[bool, str]:
    location = str(headers.get("Location") or "").lower()
    server = str(headers.get("Server") or "").lower()
    cf_ray = str(headers.get("CF-Ray") or "")
    text = body.decode("utf-8", errors="replace").lower()
    blocked = (
        _DEFAULT_DENY_FRAGMENT in text
        or "cloudflareaccess.com" in location
        or "/cdn-cgi/access/" in location
    )
    edge = bool(cf_ray or "cloudflare" in server or blocked)
    return blocked, f"HTTP {status} · cloudflare_edge={str(edge).lower()} · access_blocked={str(blocked).lower()}"


def access_get(label: str, url: str, headers: dict[str, str]) -> tuple[int | None, bool | None]:
    request = Request(
        url,
        headers={"User-Agent": "nabla-compose-cloudflare-access-diagnostic/1", **headers},
        method="GET",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - URL validated by access_url_allowed
            status = int(response.status)
            body = response.read(64 * 1024)
            blocked, detail = access_response_evidence(status, response.headers, body)
    except HTTPError as exc:
        status = int(exc.code)
        body = exc.read(64 * 1024)
        blocked, detail = access_response_evidence(status, exc.headers, body)
    except (URLError, TimeoutError, OSError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        print(f"❌ {label}: transport_error={type(exc).__name__} · {elapsed_ms}ms · {str(exc)[:240]}")
        return None, None

    elapsed_ms = round((time.monotonic() - started) * 1000)
    icon = "⚠️" if blocked else "✅"
    print(f"{icon} {label}: {detail} · {elapsed_ms}ms")
    return status, blocked


def diagnose_access(access_url: str) -> bool:
    if not access_url_allowed(access_url):
        print("❌ Access URL must be HTTPS and inside the owned albandrieu.com zone; Service Token was not sent.")
        return False

    client_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    client_id_set, client_id_len = env_state("CF_ACCESS_CLIENT_ID")
    client_secret_set, client_secret_len = env_state("CF_ACCESS_CLIENT_SECRET")
    print(
        "Access Service Token: "
        f"CF_ACCESS_CLIENT_ID={'set' if client_id_set else 'MISSING'}(len={client_id_len}) · "
        f"CF_ACCESS_CLIENT_SECRET={'set' if client_secret_set else 'MISSING'}(len={client_secret_len})"
    )

    _, anonymous_blocked = access_get("Access anonymous probe", access_url, {})
    if not client_id or not client_secret:
        print("❌ Authenticated Access probe skipped because Service Token credentials are incomplete.")
        return False

    _, service_blocked = access_get(
        "Access Service Token probe",
        access_url,
        {
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        },
    )
    if service_blocked is False:
        print("- Service Token passed the Cloudflare Access edge check.")
        return True
    if service_blocked is True:
        print(
            "- Service Token reached Cloudflare but remained Access-blocked. Verify that the Access application has a Service Auth policy whose include rule selects this exact Service Token, and check policy precedence."
        )
    elif anonymous_blocked is True:
        print("- Anonymous Access enforcement was confirmed, but the authenticated probe had a transport failure.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--access-url",
        default=os.getenv("CLOUDFLARE_ACCESS_TEST_URL", "").strip(),
        help="optional protected https://*.albandrieu.com URL to test with CF_ACCESS_CLIENT_ID/SECRET",
    )
    args = parser.parse_args()

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    account_set, account_len = env_state("CLOUDFLARE_ACCOUNT_ID")
    token_set, token_len = env_state("CLOUDFLARE_API_TOKEN")

    print("Cloudflare API diagnostic (read-only; credentials are never printed)")
    print(f"python={sys.version.split()[0]} host={socket.gethostname()}")
    print(
        "credentials: "
        f"CLOUDFLARE_ACCOUNT_ID={'set' if account_set else 'MISSING'}(len={account_len}) · "
        f"CLOUDFLARE_API_TOKEN={'set' if token_set else 'MISSING'}(len={token_len})"
    )
    print(
        "proxy env: "
        + " · ".join(
            f"{name}={'set' if os.getenv(name) else 'unset'}"
            for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")
        )
    )
    resolver_values = resolvers()
    print(f"resolvers: {', '.join(resolver_values) if resolver_values else 'not exposed'}")

    try:
        addresses = sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo("api.cloudflare.com", 443, type=socket.SOCK_STREAM)
                if item[4]
            }
        )
        print(f"✅ DNS api.cloudflare.com: {', '.join(addresses[:8])}")
    except OSError as exc:
        print(f"❌ DNS api.cloudflare.com: {type(exc).__name__}: {str(exc)[:240]}")

    if not account_id or not token:
        print("❌ Cannot test authenticated Cloudflare API: canonical observer credentials are missing.")
        if args.access_url:
            diagnose_access(args.access_url)
        return 2

    account_verify_status, account_verify_payload = api_get(
        "account token verify",
        f"/accounts/{account_id}/tokens/verify",
        token,
    )
    user_verify_status, user_verify_payload = api_get(
        "user token verify",
        "/user/tokens/verify",
        token,
    )
    tunnel_status, _ = api_get(
        "Tunnel inventory",
        f"/accounts/{account_id}/cfd_tunnel?is_deleted=false&per_page=5",
        token,
    )
    access_status, _ = api_get(
        "Access applications",
        f"/accounts/{account_id}/access/apps?per_page=5",
        token,
    )

    verify_active = token_active(account_verify_status, account_verify_payload) or token_active(
        user_verify_status,
        user_verify_payload,
    )

    print("\nInterpretation:")
    if not verify_active:
        print(
            "- Neither account-owned nor user-owned token verification confirmed an active token. Check token type, account ownership, expiry and revocation before investigating resource scopes."
        )
    elif tunnel_status == 200 and access_status == 200:
        print("- Token is active and both Tunnel + Access read paths are reachable from this runtime.")
    else:
        print("- Token is active, so failures below are account/resource scope or permission specific.")
        if tunnel_status in {401, 403}:
            print("- Tunnel API denied: add account-scoped Cloudflare Tunnel Read (or Cloudflare One Connector: cloudflared Read).")
        if access_status in {401, 403}:
            print("- Access API denied: add account-scoped Access: Apps and Policies Read.")
        if tunnel_status == 404 or access_status == 404:
            print("- An account-scoped endpoint returned 404: verify CLOUDFLARE_ACCOUNT_ID is the Account ID owning these resources.")
        if tunnel_status is None or access_status is None:
            print("- A provider request had a transport failure: inspect DNS, TLS, proxy/firewall and outbound connectivity above.")

    access_ok = True
    if args.access_url:
        print("\nProtected Access endpoint:")
        access_ok = diagnose_access(args.access_url)

    return 0 if verify_active and tunnel_status == 200 and access_status == 200 and access_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
