"""Bounded GitHub Actions API downloads with zero cross-origin credential forwarding.

This module is deliberately standard-library only: no gh CLI or GitHub runner.
"""

from __future__ import annotations

import json
import re
from urllib import error, parse, request

REPOSITORIES = frozenset({
    "AlbanAndrieu/nabla-compose",
    "AlbanAndrieu/fastapi-sample",
    "AlbanAndrieu/nabla-site-alban",
    "AlbanAndrieu/nabla-site-bababou",
})
API = "https://api.github.com/"
MAX_API_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 10_000_000
_RUNS = re.compile(
    r"^repos/AlbanAndrieu/(?P<repository>nabla-compose|fastapi-sample|nabla-site-alban|nabla-site-bababou)/actions/(?:runs/[1-9][0-9]*(?:/artifacts)?|artifacts/[1-9][0-9]*/zip|workflows/(?:security-supply-chain|nuclei-public|master-dast|production-dast|docker-build|defectdojo-trivy-handoff|defectdojo-compose-handoff)[.]yml/runs[?]branch=master&per_page=10)$"
)


class GitHubArtifactError(Exception):
    """Fail-closed source/size/provenance error without response-body leakage."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def allowed_download_url(url: str) -> bool:
    parsed = parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port in {None, 443}
        and not parsed.fragment
        and (host.endswith(".actions.githubusercontent.com")
             or host == "actions.githubusercontent.com"
             or host.endswith(".blob.core.windows.net"))
    )


def bounded_read(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise GitHubArtifactError("GitHub API response exceeds allowlisted size")
    return data


def api(route: str, token: str) -> bytes:
    """Fetch exact repo metadata or one ZIP; token is *only* sent to api.github.com."""
    match = _RUNS.fullmatch(route)
    if match is None or f"AlbanAndrieu/{match.group('repository')}" not in REPOSITORIES:
        raise GitHubArtifactError("unapproved GitHub Actions API route")
    download = route.endswith("/zip")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nabla-defectdojo-artifact-collector/1",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    target = API + route
    req = request.Request(target, headers=headers)
    try:
        with opener.open(req, timeout=20) as response:
            if download:
                raise GitHubArtifactError("archive must use GitHub's signed redirect")
            return bounded_read(response, MAX_API_BYTES)
    except error.HTTPError as exc:
        if not download or exc.code not in {302, 303, 307}:
            raise GitHubArtifactError("GitHub API request rejected") from None
        target = exc.headers.get("Location", "")
    if not allowed_download_url(target):
        raise GitHubArtifactError("archive redirect is not a trusted artifact-storage origin")
    # CRITICAL: no Authorization header (nor API token) crosses to the signed URL.
    signed = request.Request(
        target,
        headers={"User-Agent": "nabla-defectdojo-artifact-collector/1"},
    )
    try:
        with opener.open(signed, timeout=30) as response:
            return bounded_read(response, MAX_ARCHIVE_BYTES)
    except (error.URLError, TimeoutError, OSError) as exc:
        raise GitHubArtifactError("artifact retrieval failed") from None


def metadata(route: str, token: str) -> dict:
    try:
        value = json.loads(api(route, token))
    except (ValueError, UnicodeError, error.URLError):
        raise GitHubArtifactError("invalid GitHub metadata") from None
    if not isinstance(value, dict):
        raise GitHubArtifactError("unexpected metadata response")
    return value
