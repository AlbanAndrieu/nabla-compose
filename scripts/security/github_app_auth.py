"""Short-lived read-only GitHub App installation token for DefectDojo collector.

No PAT, gh CLI, Terraform state secrets or token cache. Private key is
materialized from Vaultwarden in a root-only runtime directory on TrueNAS.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib import error, request

from github_actions_artifact_api import GitHubArtifactError, NoRedirect, bounded_read

APP_RUNTIME = Path("/mnt/cpool/secrets/runtime/nabla-github-app")
CONFIG = APP_RUNTIME / "github-app.json"
PRIVATE_KEY = APP_RUNTIME / "github-app-private-key.pem"
DEFAULT_REPOSITORY = "AlbanAndrieu/nabla-site-alban"
ALLOWED_REPOSITORIES = frozenset({
    "AlbanAndrieu/nabla-compose",
    "AlbanAndrieu/fastapi-sample",
    "AlbanAndrieu/nabla-site-alban",
    "AlbanAndrieu/nabla-site-bababou",
})
MAX_JSON_BYTES = 16_384


def _verify_root_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise GitHubArtifactError("GitHub App runtime file absent or symlink")
    stat = path.stat()
    if stat.st_uid != 0 or stat.st_gid != 0 or (stat.st_mode & 0o777) != 0o600:
        raise GitHubArtifactError("GitHub App files require root:root 0600")


def configuration(repository: str = DEFAULT_REPOSITORY) -> tuple[int, int]:
    """Return App/Installation IDs; validate runtime ownership without secrets in logs."""
    if os.geteuid() != 0:
        raise GitHubArtifactError("GitHub App collector requires TrueNAS root")
    _verify_root_file(CONFIG)
    _verify_root_file(PRIVATE_KEY)
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GitHubArtifactError("invalid GitHub App metadata file") from None
    if not isinstance(config, dict) or set(config) != {"app_id", "installation_id", "repositories"}:
        raise GitHubArtifactError("unsupported GitHub App metadata fields")
    repos = config["repositories"]
    if (not isinstance(repos, list) or not repos
            or any(not isinstance(value, str) for value in repos)
            or len(set(repos)) != len(repos)
            or not set(repos).issubset(ALLOWED_REPOSITORIES)
            or repository not in repos):
        raise GitHubArtifactError("GitHub App repository scope mismatch")
    ids = config["app_id"], config["installation_id"]
    if any(type(value) is not int or value <= 0 for value in ids):
        raise GitHubArtifactError("invalid GitHub App or installation identifier")
    return ids


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def make_jwt(app_id: int, *, now: int | None = None) -> str:
    """Produce a 9-minute RS256 JWT. Only the PEM *path* appears in argv."""
    if type(app_id) is not int or app_id <= 0:
        raise GitHubArtifactError("invalid GitHub App identifier")
    timestamp = int(time.time()) if now is None else now
    header = _b64(b'{"alg":"RS256","typ":"JWT"}')
    claims = _b64(json.dumps(
        {"iat": timestamp - 60, "exp": timestamp + 540, "iss": str(app_id)},
        separators=(",", ":"),
    ).encode("ascii"))
    message = f"{header}.{claims}"
    try:
        signed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(PRIVATE_KEY)],
            input=message.encode("ascii"), capture_output=True, check=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise GitHubArtifactError("GitHub App JWT signing failed") from None
    if len(signed) < 128 or len(signed) > 1024:
        raise GitHubArtifactError("GitHub App signature size rejected")
    return f"{message}.{_b64(signed)}"


def installation_token(repository: str = DEFAULT_REPOSITORY) -> str:
    """Mint a short-lived token limited to Actions:read on one approved repository."""
    if repository not in ALLOWED_REPOSITORIES:
        raise GitHubArtifactError("GitHub App repository not allowlisted")
    app_id, installation_id = configuration(repository)
    jwt = make_jwt(app_id)
    endpoint = (
        "https://api.github.com/app/installations/"
        f"{installation_id}/access_tokens"
    )
    body = json.dumps(
        {"repositories": [repository.split("/", 1)[1]], "permissions": {"actions": "read"}},
        separators=(",", ":"),
    ).encode("ascii")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "nabla-defectdojo-artifact-collector/1",
        },
    )
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=20) as response:
            payload = json.loads(bounded_read(response, MAX_JSON_BYTES))
    except (error.URLError, OSError, ValueError, TimeoutError):
        raise GitHubArtifactError("GitHub App installation token request failed") from None
    if not isinstance(payload, dict):
        raise GitHubArtifactError("invalid GitHub App token response")
    token = payload.get("token")
    if not isinstance(token, str) or len(token) < 20 or re.search(r"\s", token):
        raise GitHubArtifactError("invalid installation token")
    permissions = payload.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("actions") != "read":
        raise GitHubArtifactError("Actions:read permission not verified")
    if set(permissions) - {"actions", "metadata"}:
        raise GitHubArtifactError("installation token has excessive permissions")
    repos = payload.get("repositories")
    if not isinstance(repos, list) or len(repos) != 1:
        raise GitHubArtifactError("installation token repository scope unverified")
    if not isinstance(repos[0], dict) or repos[0].get("full_name") != repository:
        raise GitHubArtifactError("installation token repository differs")
    try:
        expires = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise GitHubArtifactError("installation token expiry missing") from None
    seconds = (expires - datetime.now(timezone.utc)).total_seconds()
    if not 30 < seconds <= 3600:
        raise GitHubArtifactError("unexpected installation token expiry")
    return token
