#!/usr/bin/env python3
"""Read-only authenticated-surface triage for Garage S3 and LiteLLM.

Only fixed private LAN endpoints. No tokens, redirects, response bodies, or
credentials. A 401/403 can prove an HTTP responder enforced authentication,
but never proves signed S3 operations or successful model inference.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Probe:
    service: str
    name: str
    url: str
    expected_codes: frozenset[int]
    kind: str


PROBES = (
    Probe("garage", "anonymous_s3_entrypoint", "http://172.17.0.24:3900/",
          frozenset({401, 403}), "auth_boundary"),
    Probe("litellm", "anonymous_health", "http://172.17.0.24:4000/health",
          frozenset({401}), "auth_boundary"),
    Probe("litellm", "liveliness", "http://172.17.0.24:4000/health/liveliness",
          frozenset({200}), "readiness"),
)


def verdict(probe: Probe, http_code: int | None) -> dict[str, object]:
    """Do not equate anonymous auth challenges with application health."""
    if http_code is None:
        status = "unverified"
    elif http_code in probe.expected_codes:
        status = "auth_required_expected" if probe.kind == "auth_boundary" else "liveness_up"
    elif http_code in {401, 403}:
        status = "auth_required_unexpected"
    else:
        status = "unexpected_http_response"
    return {
        "service": probe.service,
        "probe": probe.name,
        "http_status": http_code,
        "state": status,
        "functional_health_proven": False,
        "scope": "truenas_lan",
    }


def request_code(probe: Probe) -> int | None:
    """Single bounded anonymous GET, no proxy or redirect and no body read."""
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(probe.url, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=4) as response:
            return response.status
    except HTTPError as error:
        return error.code
    except (URLError, OSError, TimeoutError):
        return None


def docker_health(container: str) -> str:
    """Read only the Docker Health.Status field; never print inspection JSON."""
    if container not in {"litellm", "garage"}:
        return "not_observed"
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             "{{if .State.Health}}{{.State.Health.Status}}{{else}}not_configured{{end}}",
             container],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "not_observed"
    value = result.stdout.strip()
    if result.returncode == 0 and value in {
        "healthy", "unhealthy", "starting", "not_configured",
    }:
        return value
    return "not_observed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        parser.error("only --check is supported")
    observations = [verdict(probe, request_code(probe)) for probe in PROBES]
    print(json.dumps({
        "schema_version": 1,
        "checks": observations,
        "docker_healthcheck": {
            "garage": docker_health("garage"),
            "litellm": docker_health("litellm"),
        },
        "gatus_monitor": "not_queried",
        "s3_signed_functionality": "not_queried",
        "litellm_inference": "not_queried",
        "mutations": False,
    }, sort_keys=True))
    return 0 if all(item["state"] in {
        "auth_required_expected", "liveness_up",
    } for item in observations) else 1


if __name__ == "__main__":
    raise SystemExit(main())
