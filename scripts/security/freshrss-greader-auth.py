#!/usr/bin/env python3
"""Provision a dedicated FreshRSS Google Reader Auth token without printing it.

All network I/O is opt-in (--apply or --verify); --check is entirely offline.
Two identities ONLY: securitypublic (Vercel), securityagent (private MCP).
Secret paths are local TrueNAS root-owned files, not Git or stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/freshrss/security-sources.json"
ENDPOINT = "https://freshrss.albandrieu.com/api/greader.php"
SECRET_DIR = Path("/mnt/cpool/secrets/runtime/freshrss")
ACCOUNTS = {"securitypublic", "securityagent"}
LIMIT = 1_500_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def expected_sources() -> set[str]:
    sources = json.loads(MANIFEST.read_text(encoding="utf-8"))["sources"]
    urls = {item["url"] for item in sources}
    if len(sources) != 10 or len(urls) != 10 or not all(
        url.startswith("https://") for url in urls
    ):
        raise ValueError("Invalid public source allowlist")
    return urls


def private_root() -> Path:
    root = Path(os.environ.get("FRESHRSS_SECRET_ROOT", str(SECRET_DIR)))
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Invalid secret directory")
    info = root.stat()
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Secret directory must be root:root 0700")
    return root


def read_private(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Missing or unsafe secret file")
    info = path.stat()
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("Secret file must be root:root 0600")
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if not value or "\x00" in value or "\n" in value:
        raise ValueError("Invalid secret")
    return value


def requester(url: str, *, data: bytes | None = None, token: str | None = None) -> bytes:
    headers = {"User-Agent": "nabla-freshrss-provision/1", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "GoogleLogin auth=" + token
    cf_id = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_ID")
    cf_secret = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_SECRET")
    if bool(cf_id) != bool(cf_secret):
        raise ValueError("Cloudflare Access token pair must be complete")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    with opener.open(
        Request(url, headers=headers, data=data, method="POST" if data is not None else "GET"),
        timeout=8,
    ) as response:
        if int(response.headers.get("Content-Length", "0")) > LIMIT:
            raise ValueError("Upstream response too large")
        result = response.read(LIMIT + 1)
    if len(result) > LIMIT:
        raise ValueError("Upstream response too large")
    return result


def parse_login(data: bytes, user: str) -> str:
    if len(data) > 4096:
        raise ValueError("ClientLogin response too large")
    fields = dict(line.split("=", 1) for line in data.decode("utf-8").splitlines() if "=" in line)
    token = fields.get("Auth", "")
    if not re.fullmatch(re.escape(user) + r"/[A-Za-z0-9_-]{16,128}", token):
        raise ValueError("Invalid Google Reader Auth or unexpected user")
    return token


def validate_subscriptions(token: str, expected: set[str]) -> None:
    response = requester(
        ENDPOINT + "/reader/api/0/subscription/list?output=json", token=token
    )
    document = json.loads(response)
    if not isinstance(document, dict) or not isinstance(document.get("subscriptions"), list):
        raise ValueError("Invalid subscription list")
    rows = document["subscriptions"]
    if len(rows) > 2000:
        raise ValueError("Subscription list too large")
    actual = {
        entry["url"]
        for entry in rows
        if isinstance(entry, dict) and isinstance(entry.get("url"), str)
    }
    if actual != expected or len(rows) != 10:
        raise ValueError("FreshRSS subscriptions differ from approved public allowlist")


def write_private(path: Path, token: str) -> str:
    if path.is_symlink():
        raise PermissionError("Token destination must not be a symlink")
    if path.exists():
        current = read_private(path)
        if current == token:
            return "already_present"
        if os.environ.get("FRESHRSS_ROTATION_APPROVED") != "YES":
            raise PermissionError("Token already exists; explicit rotation approval required")
    name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".greader-", delete=False
        ) as temp:
            name = temp.name
            os.chmod(name, 0o600)
            temp.write(token + "\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return "stored"


def run(user: str, mode: str) -> str:
    approved = expected_sources()
    if mode == "check":
        return f"OK: {len(approved)} allowlisted sources; no network or secret access"
    if os.geteuid() != 0:
        raise PermissionError("Provisioning and verification require root")
    root = private_root()
    token_file = root / f"{user}.greader-auth"
    if mode == "apply":
        if os.environ.get("FRESHRSS_AUTH_APPROVED") != "YES":
            raise PermissionError("FRESHRSS_AUTH_APPROVED=YES required")
        api_password = read_private(root / f"{user}.api-password")
        if len(api_password) < 24:
            raise ValueError("API password too short")
        token = parse_login(
            requester(
                ENDPOINT + "/accounts/ClientLogin",
                data=urlencode({"Email": user, "Passwd": api_password}).encode("utf-8"),
            ),
            user,
        )
    else:
        token = read_private(token_file)
        if not token.startswith(user + "/"):
            raise ValueError("Wrong account in token file")
    validate_subscriptions(token, approved)
    if mode == "verify":
        return "OK: approved subscriptions verified; token remains private"
    status = write_private(token_file, token)
    return f"OK: Google Reader token {status}; subscriptions match approved allowlist"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--user", choices=sorted(ACCOUNTS), default="securitypublic")
    args = parser.parse_args()
    mode = "check" if args.check else ("apply" if args.apply else "verify")
    try:
        print(run(args.user, mode))
        return 0
    except Exception:
        # Do not print URL, HTTP exception, Auth token, account secret or feed names.
        print("ERROR: FreshRSS GReader provisioning/verification failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
