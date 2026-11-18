#!/usr/bin/env python3
"""Bounded unauthenticated HEAD-only probes for explicitly reviewed public vhosts.

Never download .env, Terraform state, metrics, Git objects or user data. An
HTTP 200 is only a review signal; a generic SPA fallback must not be called
an exposed secret. This tests edge access, not origin firewall isolation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request

HOSTS = (
    ("manager.albandrieu.com", 443),
    ("truenas.albandrieu.com", 7000),
    ("famp-albandrieu.albandrieu.com", 443),
    ("www.albanandrieu.com", 443),
    ("www.bababou.com", 443),
)
PATHS = (
    "/.env", "/.git/config", "/.git/HEAD", "/terraform.tfstate",
    "/terraform.tfstate.backup", "/metrics", "/api", "/openapi.json",
    "/swagger-ui/", "/wp-login.php", "/wp-admin/", "/server-status",
    "/actuator/health", "/debug/pprof",
)
NEGATIVE_CONTROL = "/__nabla_absent_path_contract_20261118"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def head(host: str, port: int, path: str) -> int | None:
    url = f"https://{host}{':' + str(port) if port != 443 else ''}{path}"
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "Nabla-Public-Exposure/1.0"}
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=5) as res:
            return res.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, ValueError):
        return None


def classify(status: int | None, baseline: int | None) -> str:
    if status is None:
        return "UNVERIFIED"
    if status in (401, 403):
        return "DENIED_OBSERVED"
    if status in (404, 410):
        return "NOT_FOUND_OBSERVED"
    if 300 <= status < 400:
        return "REDIRECT_UNVERIFIED"
    if 200 <= status < 300:
        return (
            "FALLBACK_2XX_UNVERIFIED" if baseline is not None and
            200 <= baseline < 300 else "REVIEW_2XX_NOT_PROVEN"
        )
    return "UNVERIFIED"


def audit() -> dict:
    results = []
    for host, port in HOSTS:
        baseline = head(host, port, NEGATIVE_CONTROL)
        checks = []
        for path in PATHS:
            status = head(host, port, path)
            checks.append({"path": path, "status": classify(status, baseline),
                           "http_status": status})
        results.append({"hostname": host, "port": port,
                        "negative_control_http_status": baseline,
                        "checks": checks})
    return {"vantage": "github-hosted-outside-in",
            "method": "HEAD_ONLY_NO_REDIRECT_NO_RESPONSE_BODY",
            "finding_semantics": "REVIEW_NOT_CONFIRMED_EXPOSURE",
            "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit()
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    flagged = sum(
        row["status"] == "REVIEW_2XX_NOT_PROVEN"
        for host in report["results"] for row in host["checks"]
    )
    print(f"HTTP HEAD paths requiring review={flagged}; no response bodies saved")


if __name__ == "__main__":
    main()
