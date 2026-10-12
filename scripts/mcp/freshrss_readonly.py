#!/usr/bin/env python3
"""FreshRSS read-only MCP via local stdio; never exposes an HTTP listener.

Reads a dedicated FreshRSS account; returns only allowlisted public feeds.
The upstream Google Reader token is NOT scoped read-only: isolate this account.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

API = "https://freshrss.albandrieu.com/api/greader.php/reader/api/0/"
MANIFEST = Path(__file__).resolve().parents[2] / "config/freshrss/security-sources.json"
LIMIT_BYTES = 1_500_000
MAX_ARTICLES = 20
TOOLS = [
    {
        "name": "list_security_feeds",
        "description": "List approved public cyber-security RSS sources (read-only)",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "recent_security_articles",
        "description": "Get up to 20 articles from approved public feeds (read-only)",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
            "additionalProperties": False,
        },
    },
]


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def manifest_urls() -> set[str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = data["sources"]
    urls = {entry["url"] for entry in sources}
    if len(sources) != 10 or len(urls) != 10:
        raise ValueError("Manifest must include ten unique public sources")
    if not all(urlsplit(u).scheme == "https" for u in urls):
        raise ValueError("Feed URL must use HTTPS")
    return urls


def sanitize(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", value))).strip()[:limit]


def public_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    u = urlsplit(value)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password:
        return ""
    if host in {"localhost", "::1"} or host.endswith((".local", ".internal", ".int.albandrieu.com")):
        return ""
    if re.match(r"^(127|10|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.", host):
        return ""
    return value[:1024]


def read_api(path: str) -> dict:
    token = os.environ.get("FRESHRSS_MCP_AUTH", "").strip()
    if not token:
        raise RuntimeError("Not configured")
    headers = {
        "Authorization": "GoogleLogin auth=" + token,
        "Accept": "application/json",
        "User-Agent": "nabla-freshrss-readonly/1",
    }
    cf_id = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_ID")
    cf_secret = os.environ.get("FRESHRSS_CF_ACCESS_CLIENT_SECRET")
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), RejectRedirects())
    with opener.open(Request(API + path, headers=headers, method="GET"), timeout=8) as res:
        if int(res.headers.get("Content-Length", "0")) > LIMIT_BYTES:
            raise RuntimeError("Upstream too large")
        body = res.read(LIMIT_BYTES + 1)
    if len(body) > LIMIT_BYTES:
        raise RuntimeError("Upstream too large")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise RuntimeError("Invalid upstream document")
    return result


def public_subscriptions() -> tuple[list[dict], set[str]]:
    allowed = manifest_urls()
    entries = read_api("subscription/list?output=json").get("subscriptions")
    if not isinstance(entries, list) or len(entries) > 2000:
        raise RuntimeError("Invalid subscriptions")
    feeds = [
        {"id": entry["id"], "title": sanitize(entry.get("title"), 100)}
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and entry.get("url") in allowed
    ]
    return feeds, {feed["id"] for feed in feeds}


def security_articles(limit: int) -> dict:
    _feeds, approved_ids = public_subscriptions()
    articles = read_api("stream/contents/reading-list?output=json&n=100").get("items")
    if not isinstance(articles, list):
        raise RuntimeError("Invalid articles")
    result = []
    for item in articles[:100]:
        if not isinstance(item, dict) or not isinstance(item.get("origin"), dict):
            continue
        if item["origin"].get("streamId") not in approved_ids:
            continue
        candidates = item.get("canonical") or item.get("alternate") or []
        link = public_url(candidates[0].get("href")) if candidates and isinstance(candidates[0], dict) else ""
        if not link:
            continue
        excerpt = item.get("summary") or item.get("content") or {}
        result.append({
            "title": sanitize(item.get("title"), 200),
            "source": sanitize(item["origin"].get("title"), 80),
            "link": link,
            "summary": sanitize(excerpt.get("content"), 260) if isinstance(excerpt, dict) else "",
        })
        if len(result) >= limit:
            break
    return {"articles": result, "count": len(result)}


def dispatch(method: str, params: object) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "nabla-freshrss-readonly", "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method != "tools/call" or not isinstance(params, dict):
        raise ValueError("Unsupported method")
    name = params.get("name")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ValueError("Invalid arguments")
    if name == "list_security_feeds" and not args:
        feeds, _ = public_subscriptions()
        value = {"feeds": feeds, "count": len(feeds)}
    elif name == "recent_security_articles" and set(args) <= {"limit"}:
        limit = args.get("limit", 10)
        if type(limit) is not int or limit < 1 or limit > MAX_ARTICLES:
            raise ValueError("Invalid limit")
        value = security_articles(limit)
    else:
        raise ValueError("Tool not permitted")
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def main() -> None:
    for line in sys.stdin.buffer:
        if len(line) > 65536:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or "id" not in request:
                continue
            try:
                result = dispatch(request.get("method"), request.get("params"))
                response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            except (OSError, RuntimeError, ValueError, KeyError, TypeError):
                # No raw HTTP exception, token, URL or server response escapes.
                response = {
                    "jsonrpc": "2.0", "id": request["id"],
                    "error": {"code": -32000, "message": "Unavailable or operation denied"},
                }
            print(json.dumps(response, ensure_ascii=False), flush=True)
        except (ValueError, UnicodeDecodeError):
            continue


if __name__ == "__main__":
    main()
