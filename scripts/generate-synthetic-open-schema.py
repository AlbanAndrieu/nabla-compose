#!/usr/bin/env python3
"""Generate outside-in Synthetic Open Schema checks from Nabla exposure metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "catalog" / "homelab-services.json"
DEFAULT_OUTPUT = ROOT / "generated" / "synthetic-open-schema"
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CF_ID = "${CF_ACCESS_CLIENT_ID}"
_CF_SECRET = "${CF_ACCESS_CLIENT_SECRET}"


def _slug(value: object) -> str:
    text = str(value or "").strip().lower()
    return _SLUG_RE.sub("-", text).strip("-") or "service"


def _service_id(service: dict[str, Any]) -> str:
    explicit = str(service.get("id") or "").strip()
    if explicit:
        return _slug(explicit)
    raw_url = str(service.get("tunnelUrl") or "").strip()
    if raw_url:
        host = (urlsplit(raw_url).hostname or "").lower().rstrip(".")
        suffix = ".albandrieu.com"
        if host.endswith(suffix):
            prefix = host[: -len(suffix)].strip(".")
            if prefix:
                return _slug(prefix.replace(".", "-"))
    return _slug(service.get("name"))


def _access_required(service: dict[str, Any]) -> bool:
    explicit = service.get("cloudflareAccessRequired")
    if explicit is not None:
        return bool(explicit)
    return bool(service.get("external") is True and service.get("tunnelSecure") is True)


def _public_url(service: dict[str, Any]) -> str | None:
    if service.get("external") is not True or service.get("endpointEnabled") is False:
        return None
    raw = str(service.get("tunnelUrl") or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    path = str(service.get("healthPath") or "").strip()
    if path:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError(f"{_service_id(service)}: invalid healthPath")
        parsed = parsed._replace(path=path, query="", fragment="")
    elif not parsed.path:
        parsed = parsed._replace(path="/")
    return urlunsplit(parsed)


def _labels(service_id: str, access_required: bool) -> dict[str, str]:
    return {
        "nabla_service_id": service_id,
        "observer": "fastapi-cloud",
        "scope": "outside-in",
        "source": "homelab-services-transition",
        "cloudflare_access": "required" if access_required else "not-required",
    }


def _metadata(
    service: dict[str, Any],
    suffix: str,
    *,
    access_required: bool,
) -> dict[str, Any]:
    service_id = _service_id(service)
    return {
        "name": f"{service_id}-{suffix}",
        "title": f"{service.get('name') or service_id} · {suffix.upper()}",
        "labels": _labels(service_id, access_required),
    }


def _dns_check(
    service: dict[str, Any],
    hostname: str,
    *,
    access_required: bool,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "DnsCheck",
        "metadata": _metadata(service, "public-dns", access_required=access_required),
        "spec": {
            "hostname": hostname,
            "recordType": "A",
            "interval": "5m",
            "timeout": "3s",
            "retries": 1,
            "checks": [
                {
                    "type": "responseTime",
                    "operator": "lessThan",
                    "value": "2s",
                }
            ],
        },
    }


def _tls_check(
    service: dict[str, Any],
    hostname: str,
    port: int,
    *,
    access_required: bool,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "TlsCheck",
        "metadata": _metadata(service, "public-tls", access_required=access_required),
        "spec": {
            "hostname": hostname,
            "port": port,
            "interval": "6h",
            "timeout": "5s",
            "retries": 1,
            "checks": [
                {"type": "valid", "operator": "is", "value": True},
                {
                    "type": "expirationTime",
                    "operator": "greaterThan",
                    "value": "7d",
                },
            ],
        },
    }


def _http_check(
    service: dict[str, Any],
    url: str,
    *,
    access_required: bool,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "nabla-sos-outside-in/1.0",
        "Accept": "text/html,text/plain,application/json,*/*;q=0.1",
    }
    if access_required:
        headers.update(
            {
                "CF-Access-Client-Id": _CF_ID,
                "CF-Access-Client-Secret": _CF_SECRET,
            }
        )

    checks: list[dict[str, Any]] = [
        {"type": "statusCode", "operator": "greaterThan", "value": 199},
        {"type": "statusCode", "operator": "lessThan", "value": 400},
        {"type": "duration", "operator": "lessThan", "value": "5s"},
    ]
    for marker in (
        "Traceback (most recent call last)",
        "Internal Server Error",
        "Bad Gateway",
        "Service Unavailable",
    ):
        checks.append(
            {
                "type": "body",
                "operator": "notContains",
                "value": marker,
            }
        )

    return {
        "apiVersion": "v1",
        "kind": "HttpCheck",
        "metadata": _metadata(service, "public-http", access_required=access_required),
        "spec": {
            "url": url,
            "method": "GET",
            "interval": "5m",
            "timeout": "5s",
            "retries": 1,
            "headers": headers,
            "checks": checks,
        },
    }


def generate_resources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic SOS resources for explicitly public HTTPS services."""
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("catalog services must be a list")

    resources: list[dict[str, Any]] = []
    for service in sorted(
        (item for item in services if isinstance(item, dict)),
        key=_service_id,
    ):
        url = _public_url(service)
        if url is None:
            continue
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if hostname is None:
            continue
        port = parsed.port or 443
        access_required = _access_required(service)
        resources.extend(
            (
                _dns_check(service, hostname, access_required=access_required),
                _tls_check(
                    service,
                    hostname,
                    port,
                    access_required=access_required,
                ),
                _http_check(service, url, access_required=access_required),
            )
        )
    return resources


def write_resources(resources: list[dict[str, Any]], output: Path) -> None:
    """Write one runner-compatible YAML file per SOS resource."""
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    for resource in resources:
        metadata = resource["metadata"]
        path = output / f"{metadata['name']}.yaml"
        path.write_text(
            yaml.safe_dump(resource, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = json.loads(args.source.read_text(encoding="utf-8"))
    resources = generate_resources(payload)
    write_resources(resources, args.output)
    print(f"generated {len(resources)} Synthetic Open Schema checks in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
