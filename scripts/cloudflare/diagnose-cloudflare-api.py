#!/usr/bin/env python3
"""Read-only Cloudflare Tunnel/Access diagnostics without printing secrets.

The diagnostic separates transport, API-token validity, Tunnel configuration,
Access inventory and edge enforcement. Dashboard-managed Tunnel public hostnames
are read from ``GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations``
(``result.config.ingress[]``); no local cloudflared YAML is required for them.
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
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

API_BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT_SECONDS = 6.0
_DEFAULT_DENY_FRAGMENT = "this resource is blocked by this account's default-deny policy"


class _NoRedirect(HTTPRedirectHandler):
    """Keep the first Cloudflare Access response instead of following login redirects."""

    def redirect_request(  # type: ignore[override]
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_ACCESS_OPENER = build_opener(_NoRedirect)


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
        if line.startswith("nameserver "):
            value = line.split(None, 1)[1].strip()
            if value and value not in values:
                values.append(value)
    return values


def safe_payload(raw: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def result_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
        return []
    return [item for item in payload["result"] if isinstance(item, dict)]


def summarize_payload(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "non-JSON response"
    parts: list[str] = []
    if "success" in payload:
        parts.append(f"success={payload.get('success')}")
    result = payload.get("result")
    if isinstance(result, list):
        parts.append(f"result_count={len(result)}")
    elif isinstance(result, dict) and result.get("status"):
        parts.append(f"status={result.get('status')}")
    result_info = payload.get("result_info")
    if isinstance(result_info, dict) and result_info.get("total_count") is not None:
        parts.append(f"total_count={result_info.get('total_count')}")
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        if first.get("code") is not None:
            parts.append(f"error_code={first.get('code')}")
        message = str(first.get("message") or "").strip().replace("\n", " ")[:240]
        if message:
            parts.append(f"error={message}")
    return " · ".join(parts) or "response parsed"


def api_get(label: str, path: str, token: str) -> tuple[int | None, dict[str, Any] | None]:
    request = Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "nabla-compose-cloudflare-diagnostic/3",
        },
        method="GET",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS API endpoint
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
    icon = "✅" if 200 <= status < 300 else "❌"
    print(f"{icon} {label}: HTTP {status} · {elapsed_ms}ms · {summarize_payload(payload)}")
    return status, payload


def token_active(status: int | None, payload: dict[str, Any] | None) -> bool:
    return bool(
        status == 200
        and isinstance(payload, dict)
        and isinstance(payload.get("result"), dict)
        and payload["result"].get("status") == "active"
    )


def tunnel_config_hostnames(payload: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        return {}
    config = payload["result"].get("config")
    if not isinstance(config, dict) or not isinstance(config.get("ingress"), list):
        return {}
    hostnames: dict[str, str] = {}
    for rule in config["ingress"]:
        if not isinstance(rule, dict):
            continue
        hostname = str(rule.get("hostname") or "").strip().lower().rstrip(".")
        if hostname:
            hostnames[hostname] = str(rule.get("service") or "")
    return hostnames


def application_domains(payload: dict[str, Any] | None) -> set[str]:
    return {
        str(item.get("domain") or "").split("/", 1)[0].lower().rstrip(".")
        for item in result_items(payload)
        if item.get("domain")
    }


def service_token_present(payload: dict[str, Any] | None, client_id: str) -> bool | None:
    items = result_items(payload)
    if not items or not client_id:
        return None
    return any(str(item.get("client_id") or "") == client_id for item in items)


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
    access_redirect = status in {301, 302, 303, 307, 308} and (
        "cloudflareaccess.com" in location or "/cdn-cgi/access/" in location
    )
    blocked = access_redirect or _DEFAULT_DENY_FRAGMENT in text
    edge = bool(cf_ray or "cloudflare" in server or blocked)
    return blocked, (
        f"HTTP {status} · cloudflare_edge={str(edge).lower()}"
        f" · access_blocked={str(blocked).lower()}"
        f" · access_redirect={str(access_redirect).lower()}"
    )


def access_get(label: str, url: str, headers: dict[str, str]) -> tuple[int | None, bool | None]:
    request = Request(
        url,
        headers={"User-Agent": "nabla-compose-cloudflare-access-diagnostic/2", **headers},
        method="GET",
    )
    started = time.monotonic()
    try:
        with _ACCESS_OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - URL allowlisted below
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
        print("❌ Access URL must be HTTPS and inside albandrieu.com; Service Token was not sent.")
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
    if anonymous_blocked is True and service_blocked is False:
        print("✅ Anonymous request is blocked while the Service Token request passes Cloudflare Access.")
        return True
    if anonymous_blocked is True and service_blocked is True:
        print("❌ Service Token is still Access-blocked; inspect the Service Auth policy assignment/precedence.")
        return False
    if anonymous_blocked is False:
        print("⚠️ Anonymous Access was not blocked, so Service Token authentication cannot be proven from endpoint behavior.")
        return False
    print("❌ Access enforcement could not be established because one of the probes failed.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--access-url",
        default=os.getenv("CLOUDFLARE_ACCESS_TEST_URL", "").strip(),
        help="optional protected https://*.albandrieu.com URL",
    )
    parser.add_argument(
        "--tunnel-id",
        default=os.getenv("CLOUDFLARE_TUNNEL_ID", "").strip(),
        help="optional dashboard-managed Cloudflare Tunnel UUID",
    )
    parser.add_argument(
        "--expect-hostname",
        default=os.getenv("CLOUDFLARE_EXPECT_HOSTNAME", "").strip(),
        help="optional public hostname expected in Tunnel and Access inventories",
    )
    args = parser.parse_args()

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    account_set, account_len = env_state("CLOUDFLARE_ACCOUNT_ID")
    token_set, token_len = env_state("CLOUDFLARE_API_TOKEN")
    expected_hostname = args.expect_hostname.strip().lower().rstrip(".")
    if not expected_hostname and args.access_url:
        expected_hostname = (urlsplit(args.access_url).hostname or "").lower().rstrip(".")

    print("Cloudflare API diagnostic (read-only; secrets are never printed)")
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
    print(f"resolvers: {', '.join(resolvers()) or 'not exposed'}")
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
        return 2

    account_verify_status, account_verify_payload = api_get(
        "account token verify",
        f"/accounts/{account_id}/tokens/verify",
        token,
    )
    user_verify_status, user_verify_payload = api_get("user token verify", "/user/tokens/verify", token)
    verify_active = token_active(account_verify_status, account_verify_payload) or token_active(
        user_verify_status,
        user_verify_payload,
    )

    tunnel_status, tunnel_payload = api_get(
        "Tunnel inventory",
        f"/accounts/{account_id}/cfd_tunnel?is_deleted=false&per_page=100",
        token,
    )
    direct_tunnel_status: int | None = None
    direct_config_status: int | None = None
    hostname_in_tunnel: bool | None = None
    if args.tunnel_id:
        direct_tunnel_status, direct_tunnel_payload = api_get(
            "Expected Tunnel",
            f"/accounts/{account_id}/cfd_tunnel/{args.tunnel_id}",
            token,
        )
        if direct_tunnel_status == 200 and isinstance(direct_tunnel_payload, dict):
            result = direct_tunnel_payload.get("result")
            if isinstance(result, dict):
                print(
                    "  - direct tunnel: "
                    f"name={result.get('name') or 'unknown'} · status={result.get('status') or 'unknown'}"
                    f" · config_src={result.get('config_src') or 'unknown'}"
                )
        direct_config_status, direct_config_payload = api_get(
            "Tunnel public-hostname configuration",
            f"/accounts/{account_id}/cfd_tunnel/{args.tunnel_id}/configurations",
            token,
        )
        if direct_config_status == 200:
            hostnames = tunnel_config_hostnames(direct_config_payload)
            print(f"  - config.ingress hostnames: {len(hostnames)}")
            for hostname, service in sorted(hostnames.items()):
                print(f"    · {hostname} -> {service or 'origin not exposed'}")
            if expected_hostname:
                hostname_in_tunnel = expected_hostname in hostnames
                print(
                    f"  {'✅' if hostname_in_tunnel else '❌'} expected hostname {expected_hostname}: "
                    f"{'present' if hostname_in_tunnel else 'absent'}"
                )

    access_status, access_payload = api_get(
        "Access applications",
        f"/accounts/{account_id}/access/apps?per_page=100",
        token,
    )
    policy_status, _ = api_get(
        "Access reusable policies",
        f"/accounts/{account_id}/access/policies?per_page=100",
        token,
    )
    service_token_status, service_token_payload = api_get(
        "Access Service Tokens",
        f"/accounts/{account_id}/access/service_tokens?per_page=100",
        token,
    )

    print("\nInterpretation:")
    if token_active(user_verify_status, user_verify_payload) and account_verify_status == 401:
        print("- API token is user-owned; account-token verify 401 is informational, not a token failure.")
    print(f"- API token active: {str(verify_active).lower()}")
    tunnel_count = len(result_items(tunnel_payload))
    app_domains = application_domains(access_payload)
    print(f"- Tunnel objects visible: {tunnel_count}")
    print(f"- Access applications visible: {len(app_domains)}")
    if tunnel_status == 200 and tunnel_count == 0:
        print("⚠️ Tunnel list is reachable but empty despite dashboard state; verify account/token resource scope and test the known tunnel directly.")
    if access_status == 200 and not app_domains:
        print("⚠️ Access application list is reachable but empty despite dashboard state; verify account/token resource scope.")
    if args.tunnel_id and direct_tunnel_status == 200 and tunnel_count == 0:
        print("⚠️ Direct Tunnel lookup succeeds while list is empty; investigate list/filter behavior rather than declaring the Tunnel absent.")
    if direct_config_status == 200 and hostname_in_tunnel is True:
        print("✅ Expected hostname is confirmed in Cloudflare-managed config.ingress[].")
    elif direct_config_status == 200 and hostname_in_tunnel is False:
        print("❌ Tunnel configuration is readable but expected hostname is genuinely absent from config.ingress[].")
    if expected_hostname:
        print(
            f"  {'✅' if expected_hostname in app_domains else '❌'} Access application for {expected_hostname}: "
            f"{'present' if expected_hostname in app_domains else 'absent'}"
        )
    token_match = service_token_present(service_token_payload, os.getenv("CF_ACCESS_CLIENT_ID", "").strip())
    if token_match is not None:
        print(
            f"  {'✅' if token_match else '❌'} configured CF_ACCESS_CLIENT_ID: "
            f"{'present' if token_match else 'not found'} in Service Token inventory"
        )

    access_ok = True
    if args.access_url:
        print("\nProtected Access endpoint (redirects disabled):")
        access_ok = diagnose_access(args.access_url)

    api_ok = bool(verify_active and tunnel_status == 200 and access_status == 200 and policy_status == 200)
    if args.tunnel_id:
        api_ok = bool(api_ok and direct_tunnel_status == 200 and direct_config_status == 200)
    if args.tunnel_id and expected_hostname:
        api_ok = bool(api_ok and hostname_in_tunnel is True)
    if service_token_status not in {200, 403}:
        api_ok = False
    return 0 if api_ok and access_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
