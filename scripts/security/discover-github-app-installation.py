#!/usr/bin/env python3
"""Discover GitHub App installation ID after owner-approved Manifest registration.

--check is offline. --apply updates only a private bootstrap metadata file,
and never creates/installs an App or touches DefectDojo.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from urllib import error, request

import github_app_auth as auth
from github_actions_artifact_api import GitHubArtifactError, NoRedirect, bounded_read

REPO = "AlbanAndrieu/nabla-site-bababou"
MAX_BYTES = 16_384


def query_installation() -> dict:
    auth._verify_root_file(auth.CONFIG)
    auth._verify_root_file(auth.PRIVATE_KEY)
    if os.geteuid() != 0:
        raise GitHubArtifactError("runtime installation discovery requires root")
    config = json.loads(auth.CONFIG.read_text(encoding="utf-8"))
    if (not isinstance(config, dict) or set(config) != {
        "app_id", "installation_id", "repositories"
    } or not isinstance(config.get("repositories"), list)
            or set(config["repositories"]) != auth.ALLOWED_REPOSITORIES
            or len(config["repositories"]) != len(auth.ALLOWED_REPOSITORIES)):
        raise GitHubArtifactError("private metadata does not match desired repository scope")
    app_id = config.get("app_id")
    if type(app_id) is not int or app_id <= 0:
        raise GitHubArtifactError("invalid GitHub App ID")
    jwt = auth.make_jwt(app_id)
    req = request.Request(
        f"https://api.github.com/repos/{REPO}/installation",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "nabla-defectdojo-app-provisioning",
        },
    )
    try:
        with request.build_opener(request.ProxyHandler({}), NoRedirect()).open(
            req, timeout=20
        ) as response:
            installed = json.loads(bounded_read(response, MAX_BYTES))
    except (error.URLError, OSError, ValueError, TimeoutError):
        raise GitHubArtifactError("GitHub App installation not verified") from None
    if (not isinstance(installed, dict)
            or installed.get("app_id") != app_id
            or installed.get("account", {}).get("login") != "AlbanAndrieu"
            or installed.get("repository_selection") != "selected"
            or installed.get("permissions", {}).get("actions") != "read"
            or set(installed.get("permissions", {})) - {"actions", "metadata"}
            or type(installed.get("id")) is not int or installed["id"] <= 0):
        raise GitHubArtifactError("GitHub App installation violates read-only policy")
    identifier = config.get("installation_id")
    if type(identifier) is not int or (identifier not in (0, installed["id"])):
        raise GitHubArtifactError("installation ID drift; refusing overwrite")
    config["installation_id"] = installed["id"]
    return config


def write_metadata(config: dict) -> None:
    directory = auth.CONFIG.parent
    fd, temp = tempfile.mkstemp(prefix=".github-app-id-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, auth.CONFIG)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if args.check:
        print("CHECK: GitHub App installation discovery is offline; no key accessed")
        return 0
    config = query_installation()
    write_metadata(config)
    print("PASS: selected read-only installation verified; metadata updated privately")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, GitHubArtifactError) as exc:
        raise SystemExit("REJECTED: GitHub App installation cannot be verified") from None
