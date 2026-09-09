"""Build a bounded read-only OpenAPI document for production ZAP scanning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

READ_ONLY_METHODS = frozenset({"get", "head", "options"})
DENIED_TEXT_MARKERS = (
    "pfsense",
    "snort",
    "pfblocker",
    "pf_blocker",
)
DENIED_PATHS = frozenset(
    {
        "/healthz",
        "/sickz",
        "/readyz",
        "/api/homelab/status",
        "/api/homelab/health",
    }
)


def _load_json(source: str, timeout: float) -> dict[str, object]:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(
            source,
            headers={
                "Accept": "application/json",
                "User-Agent": "nabla-compose-zap-openapi/1",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    else:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("OpenAPI document must be a JSON object")
    if not isinstance(payload.get("paths"), dict):
        raise ValueError("OpenAPI document must contain an object-valued paths field")
    return payload


def _operation_text(path: str, operation: object) -> str:
    if not isinstance(operation, dict):
        return path.lower()
    values: list[str] = [path]
    for key in ("summary", "description", "operationId"):
        value = operation.get(key)
        if isinstance(value, str):
            values.append(value)
    tags = operation.get("tags")
    if isinstance(tags, list):
        values.extend(str(tag) for tag in tags)
    return " ".join(values).lower()


def _is_denied(path: str, operation: object) -> bool:
    normalized = path.rstrip("/") or "/"
    if normalized in DENIED_PATHS:
        return True
    text = _operation_text(path, operation)
    return any(marker in text for marker in DENIED_TEXT_MARKERS)


def filter_openapi(
    document: dict[str, object],
    *,
    server_url: str,
) -> tuple[dict[str, object], list[str]]:
    paths = document["paths"]
    assert isinstance(paths, dict)

    filtered_paths: dict[str, object] = {}
    excluded: list[str] = []

    for path, raw_item in paths.items():
        if not isinstance(path, str) or not isinstance(raw_item, dict):
            continue

        kept_item: dict[str, object] = {}
        for key, value in raw_item.items():
            method = key.lower()
            if method not in READ_ONLY_METHODS:
                if method in {
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "trace",
                }:
                    excluded.append(f"{method.upper()} {path}: non-read-only method")
                continue
            if _is_denied(path, value):
                excluded.append(f"{method.upper()} {path}: pfSense/high-cost exclusion")
                continue
            kept_item[key] = value

        # Retain OpenAPI path-level metadata only when at least one operation survived.
        if kept_item:
            for key in ("parameters", "$ref"):
                if key in raw_item:
                    kept_item[key] = raw_item[key]
            filtered_paths[path] = kept_item

    if not filtered_paths:
        raise ValueError("OpenAPI filter removed every operation; refusing empty DAST input")

    filtered = dict(document)
    filtered["servers"] = [{"url": server_url.rstrip("/")}]
    filtered["paths"] = filtered_paths
    return filtered, sorted(set(excluded))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a read-only OpenAPI document for ZAP while excluding "
            "pfSense-backed/high-cost runtime probes."
        )
    )
    parser.add_argument("--source", required=True, help="OpenAPI JSON URL or local file")
    parser.add_argument("--output", required=True, help="Filtered JSON output path")
    parser.add_argument("--server-url", required=True, help="API server URL for ZAP")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        document = _load_json(args.source, args.timeout)
        filtered, excluded = filter_openapi(document, server_url=args.server_url)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(filtered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    paths = filtered["paths"]
    assert isinstance(paths, dict)
    operation_count = sum(
        1
        for item in paths.values()
        if isinstance(item, dict)
        for method in item
        if method.lower() in READ_ONLY_METHODS
    )
    print(
        f"Prepared ZAP OpenAPI: paths={len(paths)} "
        f"read_only_operations={operation_count} excluded={len(excluded)}"
    )
    for item in excluded:
        print(f"  excluded: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
