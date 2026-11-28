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
    r"^repos/AlbanAndrieu/(?P<repository>nabla-compose|fastapi-sample|nabla-site-alban|nabla-site-bababou)/actions/(?:runs/[1-9][0-9]*(?:/artifacts|/jobs[?]per_page=100)?|artifacts/[1-9][0-9]*/zip|workflows/(?:security-supply-chain|nuclei-public|master-dast|production-dast|docker-build|defectdojo-trivy-handoff|defectdojo-compose-handoff|external-attack-surface)[.]yml/runs[?]branch=master&per_page=10)$"
)


class GitHubArtifactError(Exception):
    """Fail-closed source/size/provenance error without response-body leakage."""


# Only locally authored reason codes may reach logs. Never print exception
# bodies, URLs, underlying OSError text, redirect locations or headers.
SAFE_REASONS = {
    "GitHub App runtime file absent or symlink": "APP_RUNTIME_MISSING",
    "GitHub App files require root:root 0600": "APP_RUNTIME_PERMISSIONS",
    "GitHub App collector requires TrueNAS root": "APP_REQUIRES_ROOT",
    "invalid GitHub App metadata file": "APP_METADATA_INVALID",
    "unsupported GitHub App metadata fields": "APP_METADATA_SCHEMA",
    "GitHub App repository scope mismatch": "APP_REPOSITORY_NOT_CONFIGURED",
    "invalid GitHub App or installation identifier": "APP_INSTALLATION_ID_INVALID",
    "GitHub App JWT signing failed": "APP_JWT_SIGN_FAILED",
    "GitHub App signature size rejected": "APP_JWT_SIGNATURE_INVALID",
    "invalid GitHub App identifier": "APP_ID_INVALID",
    "GitHub App repository not allowlisted": "APP_REPOSITORY_NOT_ALLOWED",
    "GitHub App installation token request failed": "APP_TOKEN_TRANSPORT",
    "invalid GitHub App token response": "APP_TOKEN_RESPONSE_INVALID",
    "invalid installation token": "APP_TOKEN_INVALID",
    "Actions:read permission not verified": "APP_ACTIONS_READ_MISSING",
    "installation token has excessive permissions": "APP_TOKEN_EXCESS_PERMISSIONS",
    "installation token repository scope unverified": "APP_TOKEN_SCOPE_UNVERIFIED",
    "installation token repository differs": "APP_TOKEN_REPO_MISMATCH",
    "installation token expiry missing": "APP_TOKEN_EXPIRY_INVALID",
    "unexpected installation token expiry": "APP_TOKEN_EXPIRY_INVALID",
    "GitHub API response exceeds allowlisted size": "GITHUB_RESPONSE_TOO_LARGE",
    "unapproved GitHub Actions API route": "GITHUB_ROUTE_NOT_ALLOWED",
    "archive must use GitHub's signed redirect": "ARTIFACT_REDIRECT_MISSING",
    "GitHub API request rejected": "GITHUB_API_REJECTED",
    "archive redirect is not a trusted artifact-storage origin": "ARTIFACT_REDIRECT_DENIED",
    "artifact retrieval failed": "ARTIFACT_DOWNLOAD_FAILED",
    "invalid GitHub metadata": "GITHUB_METADATA_INVALID",
    "unexpected metadata response": "GITHUB_METADATA_SCHEMA",
    "GitHub API transport failed": "GITHUB_API_TRANSPORT",
}


def safe_reason(exc: GitHubArtifactError) -> str:
    if len(exc.args) == 2 and exc.args[0] in (
        "APP_TOKEN_HTTP", "GITHUB_API_HTTP", "ARTIFACT_STORAGE_HTTP"
    ) and type(exc.args[1]) is int and 400 <= exc.args[1] <= 599:
        return f"{exc.args[0]}_{exc.args[1]}"
    if len(exc.args) == 1 and isinstance(exc.args[0], str):
        return SAFE_REASONS.get(exc.args[0], "UNCLASSIFIED")
    return "UNCLASSIFIED"


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
            raise GitHubArtifactError("GITHUB_API_HTTP", exc.code) from None
        target = exc.headers.get("Location", "")
    except (error.URLError, TimeoutError, OSError):
        raise GitHubArtifactError("GitHub API transport failed") from None
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
    except error.HTTPError as exc:
        raise GitHubArtifactError("ARTIFACT_STORAGE_HTTP", exc.code) from None
    except (error.URLError, TimeoutError, OSError):
        raise GitHubArtifactError("artifact retrieval failed") from None


def metadata(route: str, token: str) -> dict:
    try:
        value = json.loads(api(route, token))
    except (ValueError, UnicodeError, error.URLError):
        raise GitHubArtifactError("invalid GitHub metadata") from None
    if not isinstance(value, dict):
        raise GitHubArtifactError("unexpected metadata response")
    return value
