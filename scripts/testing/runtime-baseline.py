from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class HttpResult:
    method: str
    url: str
    status: int
    elapsed_ms: float
    headers: dict[str, str]
    body: bytes


def _headers_from_env() -> dict[str, str]:
    headers: dict[str, str] = {}
    client_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret
    return headers


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urllib.parse.urljoin(base, path.lstrip("/"))


def _request(
    url: str,
    *,
    method: str = "GET",
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> HttpResult:
    request_headers = {
        "User-Agent": "nabla-compose-runtime-baseline/1",
        "Accept": "application/json, */*;q=0.1",
    }
    request_headers.update(_headers_from_env())
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, method=method, headers=request_headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read(1024 * 1024)
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return HttpResult(
        method=method,
        url=url,
        status=status,
        elapsed_ms=elapsed_ms,
        headers=response_headers,
        body=body,
    )


def _json_body(result: HttpResult) -> object:
    try:
        return json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{result.method} {result.url} did not return valid JSON"
        ) from exc


def run_integration(args: argparse.Namespace) -> int:
    failures: list[str] = []
    evidence: list[dict[str, object]] = []
    for path in (args.health_path, args.version_path):
        url = _join_url(args.url, path)
        try:
            result = _request(url, timeout=args.timeout)
        except (OSError, urllib.error.URLError) as exc:
            failures.append(f"{path}: request failed: {exc}")
            continue

        item: dict[str, object] = {
            "path": path,
            "status": result.status,
            "elapsed_ms": round(result.elapsed_ms, 2),
        }
        if result.status != 200:
            failures.append(f"{path}: expected HTTP 200, got {result.status}")
        try:
            payload = _json_body(result)
            item["json_type"] = type(payload).__name__
            if not isinstance(payload, (dict, list)):
                failures.append(f"{path}: expected a JSON object or array")
        except ValueError as exc:
            failures.append(str(exc))
        evidence.append(item)

    print(json.dumps({"mode": "integration", "checks": evidence}, indent=2))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


def _cookie_security_failures(result: HttpResult, https: bool) -> list[str]:
    raw_cookie = result.headers.get("set-cookie", "")
    if not raw_cookie:
        return []
    failures: list[str] = []
    lower = raw_cookie.lower()
    if "httponly" not in lower:
        failures.append("Set-Cookie is missing HttpOnly")
    if https and "secure" not in lower:
        failures.append("Set-Cookie is missing Secure on HTTPS")
    return failures


def run_pentest(args: argparse.Namespace) -> int:
    parsed = urllib.parse.urlparse(args.url)
    failures: list[str] = []
    warnings: list[str] = []

    if parsed.scheme not in {"http", "https"}:
        failures.append("target URL must use http:// or https://")
    if parsed.scheme != "https" and not args.allow_http:
        failures.append("HTTPS is required unless --allow-http is explicitly set")

    health_url = _join_url(args.url, args.health_path)
    try:
        get_result = _request(health_url, timeout=args.timeout)
        trace_result = _request(health_url, method="TRACE", timeout=args.timeout)
    except (OSError, urllib.error.URLError) as exc:
        print(f"FAIL: request failed: {exc}", file=sys.stderr)
        return 1

    if get_result.status != 200:
        failures.append(f"health endpoint returned HTTP {get_result.status}")
    if 200 <= trace_result.status < 300:
        failures.append(f"TRACE is enabled (HTTP {trace_result.status})")

    headers = get_result.headers
    if headers.get("x-content-type-options", "").lower() != "nosniff":
        failures.append("X-Content-Type-Options: nosniff is missing")

    csp = headers.get("content-security-policy", "")
    xfo = headers.get("x-frame-options", "")
    if not xfo and "frame-ancestors" not in csp.lower():
        failures.append(
            "frame protection is missing (X-Frame-Options or CSP frame-ancestors)"
        )

    if parsed.scheme == "https" and "strict-transport-security" not in headers:
        failures.append("Strict-Transport-Security is missing on HTTPS")

    allow_origin = headers.get("access-control-allow-origin", "")
    allow_credentials = headers.get("access-control-allow-credentials", "").lower()
    if allow_origin == "*" and allow_credentials == "true":
        failures.append("dangerous CORS combination: wildcard origin with credentials")

    failures.extend(_cookie_security_failures(get_result, parsed.scheme == "https"))

    server = headers.get("server", "")
    if server and re.search(r"\d+\.\d+", server):
        warnings.append(f"Server header appears versioned: {server}")

    content_type = headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        warnings.append(f"health Content-Type is not JSON: {content_type or '<missing>'}")

    report = {
        "mode": "pentest",
        "target": args.url,
        "health_status": get_result.status,
        "trace_status": trace_result.status,
        "elapsed_ms": round(get_result.elapsed_ms, 2),
        "warnings": warnings,
        "failures": failures,
    }
    print(json.dumps(report, indent=2))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    rank = max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1)
    return ordered[rank]


def run_performance(args: argparse.Namespace) -> int:
    if args.requests < 1:
        raise ValueError("--requests must be >= 1")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be >= 1")
    if args.max_p95_ms <= 0:
        raise ValueError("--max-p95-ms must be > 0")
    if not 0 <= args.max_error_rate <= 1:
        raise ValueError("--max-error-rate must be between 0 and 1")

    url = _join_url(args.url, args.path)

    def one_request(_: int) -> tuple[bool, float, int | None]:
        try:
            result = _request(url, timeout=args.timeout)
            return result.status == 200, result.elapsed_ms, result.status
        except (OSError, urllib.error.URLError):
            return False, args.timeout * 1000.0, None

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        results = list(executor.map(one_request, range(args.requests)))

    latencies = [elapsed for _, elapsed, _ in results]
    failures = sum(1 for ok, _, _ in results if not ok)
    error_rate = failures / len(results)
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    maximum = max(latencies)

    report = {
        "mode": "performance",
        "target": url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "errors": failures,
        "error_rate": round(error_rate, 4),
        "latency_ms": {
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "max": round(maximum, 2),
        },
        "thresholds": {
            "max_p95_ms": args.max_p95_ms,
            "max_error_rate": args.max_error_rate,
        },
    }
    print(json.dumps(report, indent=2))

    failed = False
    if error_rate > args.max_error_rate:
        print(
            f"FAIL: error rate {error_rate:.2%} exceeds {args.max_error_rate:.2%}",
            file=sys.stderr,
        )
        failed = True
    if p95 > args.max_p95_ms:
        print(
            f"FAIL: p95 {p95:.2f}ms exceeds {args.max_p95_ms:.2f}ms",
            file=sys.stderr,
        )
        failed = True
    return int(failed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Non-destructive HTTP integration, security and performance baselines."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    integration = subparsers.add_parser(
        "integration", help="Validate health/version application contracts."
    )
    integration.add_argument("--url", required=True)
    integration.add_argument("--health-path", default="/health")
    integration.add_argument("--version-path", default="/v2/version")
    integration.add_argument("--timeout", type=float, default=5.0)
    integration.set_defaults(func=run_integration)

    pentest = subparsers.add_parser(
        "pentest", help="Run a read-only HTTP security baseline."
    )
    pentest.add_argument("--url", required=True)
    pentest.add_argument("--health-path", default="/health")
    pentest.add_argument("--timeout", type=float, default=5.0)
    pentest.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow cleartext HTTP for trusted local test targets.",
    )
    pentest.set_defaults(func=run_pentest)

    performance = subparsers.add_parser(
        "performance", help="Run a small bounded HTTP load/latency smoke."
    )
    performance.add_argument("--url", required=True)
    performance.add_argument("--path", default="/health")
    performance.add_argument("--requests", type=int, default=25)
    performance.add_argument("--concurrency", type=int, default=5)
    performance.add_argument("--timeout", type=float, default=5.0)
    performance.add_argument("--max-p95-ms", type=float, default=1000.0)
    performance.add_argument("--max-error-rate", type=float, default=0.02)
    performance.set_defaults(func=run_performance)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
