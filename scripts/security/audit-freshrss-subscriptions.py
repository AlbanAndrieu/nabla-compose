#!/usr/bin/env python3
"""Read-only FreshRSS acceptance: validate exactly ten approved subscriptions.

--check only inspects versioned files. --verify uses a dedicated GReader Auth
from the environment, discloses neither token nor feed URLs, fails closed.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
from pathlib import Path
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/freshrss/security-sources.json"
OPML = ROOT / "config/freshrss/public-security.opml"
ENDPOINT = "https://freshrss.albandrieu.com/api/greader.php/reader/api/0/subscription/list?output=json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def expected_urls() -> set[str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = data["sources"]
    urls = {row["url"] for row in raw}
    if len(raw) != 10 or len(urls) != 10 or not all(url.startswith("https://") for url in urls):
        raise ValueError("Invalid source manifest")
    xml = OPML.read_text(encoding="utf-8").replace("&amp;", "&")
    for url in urls:
        if url not in xml:
            raise ValueError("OPML does not match manifest")
    return urls


def verify(expected: set[str]) -> bool:
    token = os.environ.get("FRESHRSS_AUDIT_AUTH", "").strip()
    if not token:
        raise ValueError("FRESHRSS_AUDIT_AUTH is not configured")
    headers = {"Authorization": "GoogleLogin auth=" + token, "Accept": "application/json"}
    cfid = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_ID")
    cfsecret = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_SECRET")
    if cfid and cfsecret:
        headers["CF-Access-Client-Id"] = cfid
        headers["CF-Access-Client-Secret"] = cfsecret
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    with opener.open(Request(ENDPOINT, headers=headers, method="GET"), timeout=8) as response:
        if int(response.headers.get("Content-Length", "0")) > 1_500_000:
            raise ValueError("Response exceeds size limit")
        data = response.read(1_500_001)
    if len(data) > 1_500_000:
        raise ValueError("Response exceeds size limit")
    obj = json.loads(data)
    if not isinstance(obj.get("subscriptions"), list):
        raise ValueError("Invalid subscription list")
    actual = {row.get("url") for row in obj["subscriptions"] if isinstance(row, dict)}
    missing = expected - actual
    extra = actual - expected
    print(f"FreshRSS subscriptions: approved={len(expected)} observed={len(actual)} missing={len(missing)} unexpected={len(extra)}")
    return not missing and not extra


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("--check", "--verify"), default="--check")
    args = parser.parse_args()
    try:
        expected = expected_urls()
        if args.mode == "--check":
            print(f"OK: manifest and OPML contain {len(expected)} approved public sources; no network call")
            return 0
        if verify(expected):
            print("OK: exact subscription parity; ready for privacy review")
            return 0
        print("ERROR: FreshRSS subscription parity failed; do not publish")
        return 1
    except Exception:
        # Never print exception strings that might contain credentials or private URLs.
        print("ERROR: FreshRSS audit not accepted; inspect protected logs and connectivity")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
