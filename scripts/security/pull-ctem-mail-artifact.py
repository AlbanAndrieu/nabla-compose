#!/usr/bin/env python3
"""Read-only GitHub App pull of the existing minimized checkdmarc artifact.

Uses the existing GitHub App's Actions:read token and exact API allowlists.
Only the newest master scheduled/manual run is eligible; no stale fallback.
--check is offline, --pull stages privately, --store also persists to shared PG.
Never imports automatically into DefectDojo or publishes raw DNS evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from zipfile import ZipFile, BadZipFile

SECURITY = Path(__file__).resolve().parent
sys.path.insert(0, str(SECURITY))
from github_actions_artifact_api import api, metadata, GitHubArtifactError, safe_reason
from github_app_auth import installation_token

REPO = "AlbanAndrieu/nabla-compose"
WORKFLOW = "external-attack-surface.yml"
WORKFLOW_NAME = "External attack surface (homelab)"
REPORT_FILE = "public-mail-deep.json"
REPORT_ROOT = Path("/mnt/cpool/ctem/amass/reports/mail")
MAX_ZIP = 4_000_000
MAX_JSON = 2_000_000
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class CtemMailPullError(Exception):
    """Sanitized failure; do not expose connector response or private payload."""


def selected_run(rows: list[dict], now: datetime | None = None) -> dict:
    if not isinstance(rows, list) or len(rows) > 10:
        raise CtemMailPullError("RUN_LIST_INVALID")
    candidates = [
        x for x in rows if isinstance(x, dict)
        and x.get("name") == WORKFLOW_NAME
        and x.get("head_branch") == "master"
        and x.get("event") in ("schedule", "workflow_dispatch")
        and type(x.get("id")) is int and x["id"] > 0
        and isinstance(x.get("head_sha"), str)
        and SHA40.fullmatch(x["head_sha"])
    ]
    if not candidates:
        raise CtemMailPullError("NO_ELIGIBLE_MASTER_RUN")
    latest = max(candidates, key=lambda x: x["id"])
    if latest.get("conclusion") != "success" or latest.get("status") != "completed":
        raise CtemMailPullError("LATEST_RUN_NOT_SUCCESSFUL")
    stamp = latest.get("created_at")
    try:
        checked = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise CtemMailPullError("RUN_TIME_INVALID") from exc
    current = now or datetime.now(timezone.utc)
    if (checked.tzinfo is None or not timedelta(0) <= current - checked
            <= timedelta(days=7)):
        raise CtemMailPullError("RUN_STALE")
    return latest


def chosen_artifact(rows: list[dict], run_id: int) -> dict:
    if not isinstance(rows, list):
        raise CtemMailPullError("ARTIFACT_LIST_INVALID")
    matches = [
        x for x in rows if isinstance(x, dict)
        and x.get("name") == f"public-mail-deep-{run_id}"
        and x.get("expired") is False
        and type(x.get("id")) is int and x["id"] > 0
        and type(x.get("size_in_bytes")) is int and 0 < x["size_in_bytes"] <= MAX_ZIP
    ]
    if len(matches) != 1:
        raise CtemMailPullError("ARTIFACT_MISSING_OR_AMBIGUOUS")
    return matches[0]


def extract_report(content: bytes) -> bytes:
    if not 0 < len(content) <= MAX_ZIP:
        raise CtemMailPullError("ARTIFACT_TOO_LARGE")
    try:
        with ZipFile(BytesIO(content)) as zipfile:
            entries = zipfile.infolist()
            if (len(entries) != 1 or entries[0].filename != REPORT_FILE
                    or entries[0].is_dir() or entries[0].file_size > MAX_JSON
                    or entries[0].compress_size > MAX_ZIP
                    or (entries[0].external_attr >> 16) & 0o170000 == 0o120000):
                raise CtemMailPullError("ARTIFACT_MEMBER_DENIED")
            report = zipfile.read(REPORT_FILE)
    except (BadZipFile, OSError, RuntimeError, KeyError, ValueError):
        raise CtemMailPullError("ARTIFACT_ZIP_INVALID") from None
    if not 0 < len(report) <= MAX_JSON:
        raise CtemMailPullError("ARTIFACT_REPORT_INVALID")
    return report


def report_validator():
    spec = importlib.util.spec_from_file_location(
        "ctem_reports", SECURITY / "store-ctem-summary.py"
    )
    if spec is None or spec.loader is None:
        raise CtemMailPullError("CTEM_VALIDATOR_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_dir(path: Path) -> None:
    if path.is_symlink():
        raise CtemMailPullError("PRIVATE_INBOX_SYMLINK")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise CtemMailPullError("PRIVATE_INBOX_PERMISSIONS")


def stage_report(report: bytes, run_id: int, dest: Path, store: bool = False) -> str:
    private_dir(dest)
    path = dest / f"public-mail-deep-{run_id}.json"
    if path.is_symlink():
        raise CtemMailPullError("PRIVATE_REPORT_SYMLINK")
    if path.exists():
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600
                or path.read_bytes() != report):
            raise CtemMailPullError("STAGED_REPORT_CHANGED")
        outcome = "ALREADY_STAGED"
    else:
        fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(report)
        outcome = "STAGED"
    validator = report_validator()
    receipt, digest, encoded = validator.validate_receipt("checkdmarc", path)
    if store:
        validator.store(receipt, digest, encoded, validator.secret_password())
        outcome = "STORED"
    return outcome


def run(should_store: bool, *, report_root: Path = REPORT_ROOT) -> str:
    from github_app_auth import installation_token
    token = installation_token(REPO)
    runs = metadata(
        f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?branch=master&per_page=10",
        token,
    ).get("workflow_runs")
    run_info = selected_run(runs)
    run_id = run_info["id"]
    current_run = metadata(f"repos/{REPO}/actions/runs/{run_id}", token)
    if any(current_run.get(k) != run_info.get(k) for k in (
            "id", "head_sha", "head_branch", "name", "status", "conclusion")):
        raise CtemMailPullError("RUN_PROVENANCE_CHANGED")
    artifact_rows = metadata(
        f"repos/{REPO}/actions/runs/{run_id}/artifacts", token
    ).get("artifacts")
    artifact = chosen_artifact(artifact_rows, run_id)
    archive = api(f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip", token)
    report = extract_report(archive)
    result = stage_report(report, run_id, report_root, should_store)
    print(f"ctem_checkdmarc={result}; workflow_run_id={run_id}; "
          "no raw DNS records or candidate names logged")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--pull", action="store_true")
    mode.add_argument("--store", action="store_true")
    opts = parser.parse_args()
    if opts.check:
        print("CHECK: existing GitHub App Actions:read; latest successful master run only")
        print("CHECK: single public-mail-deep.json artifact; private store, no Dojo auto import")
        return 0
    if os.geteuid() != 0 or os.environ.get("CTEM_MAIL_PULL_APPROVED") != "YES":
        parser.error("TrueNAS root and CTEM_MAIL_PULL_APPROVED=YES required")
    if opts.store and os.environ.get("CTEM_REPORT_STORE_APPROVED") != "YES":
        parser.error("CTEM_REPORT_STORE_APPROVED=YES required")
    run(opts.store)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CtemMailPullError, GitHubArtifactError, ValueError, OSError,
            RuntimeError, json.JSONDecodeError) as exc:
        label = (exc.args[0] if isinstance(exc, CtemMailPullError) else
                 safe_reason(exc) if isinstance(exc, GitHubArtifactError)
                 else "CTEM_MAIL_REJECTED")
        raise SystemExit(f"REJECTED: {label}") from None
