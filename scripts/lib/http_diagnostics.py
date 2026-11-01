"""Bounded, no-redirect HTTP probes for read-only homelab diagnostics.

Callers must create an opener with ProxyHandler({}) and NoRedirect
so an environment proxy cannot silently change the observation origin.
Neither the returned error category nor exceptions contain response bodies.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    """Prevent cross-origin redirect follow-up for a diagnostic probe."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_status(opener: Any, url: str, *, timeout: int) -> int:
    """Return only an HTTP status, or 0 when transport cannot be verified."""
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with opener.open(request, timeout=timeout) as response:
            status = response.status
        return status if type(status) is int and 100 <= status <= 599 else 0
    except HTTPError as exc:
        try:
            code = exc.code
            return code if type(code) is int and 100 <= code <= 599 else 0
        finally:
            exc.close()
    except (OSError, ValueError):
        return 0


def _read_json(opener: Any, url: str, *, timeout: int, limit: int) -> Any:
    """Read one bounded JSON response without reflecting payloads in errors.

    The caller owns the opener and therefore the no-proxy/no-redirect policy.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("invalid response limit")
    request = Request(url, headers={"Accept": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("response too large")
    try:
        return json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError("invalid JSON response") from None


def read_json_object(opener: Any, url: str, *, timeout: int, limit: int) -> dict[str, Any]:
    """Read a bounded JSON object, preserving the established API contract."""
    parsed = _read_json(opener, url, timeout=timeout, limit=limit)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return parsed


def read_json_array(opener: Any, url: str, *, timeout: int, limit: int) -> list[Any]:
    """Read a bounded JSON array, e.g. Gatus endpoint status observations."""
    parsed = _read_json(opener, url, timeout=timeout, limit=limit)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON array")
    return parsed
