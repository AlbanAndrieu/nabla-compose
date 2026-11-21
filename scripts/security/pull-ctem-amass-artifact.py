"""Pull exactly one external Amass counts-only artifact via existing GitHub App.

Manual run-id only: active discovery is never scheduled nor assumed complete.
No raw discovered hostnames, no direct PostgreSQL connection from GitHub.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import sys
from zipfile import BadZipFile, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_actions_artifact_api import api, metadata, GitHubArtifactError, safe_reason
from github_app_auth import installation_token

REPO = "AlbanAndrieu/nabla-compose"
WORKFLOW = "External attack surface (homelab)"
TARGET = "public-amass-summary.json"
PRIVATE_ROOT = Path("/mnt/cpool/ctem/amass/reports/external")
MAX_ARCHIVE = 4_000_000
MAX_REPORT = 2_000_000
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


def verify_run(run: dict, run_id: int, now: datetime | None = None) -> None:
    if (run.get("id") != run_id or run.get("name") != WORKFLOW
            or run.get("head_branch") != "master" or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or not SHA40.fullmatch(str(run.get("head_sha", "")))):
        raise ValueError("external Amass run is not approved complete master workflow")
    stamp = datetime.fromisoformat(str(run["created_at"]).replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or not timedelta(0) <= current - stamp <= timedelta(days=7):
        raise ValueError("external Amass run outside artifact retention period")


def verify_artifact(items: list, run_id: int) -> int:
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("invalid artifact listing")
    matches = [x for x in items if isinstance(x, dict)
               and x.get("name") == f"public-amass-summary-{run_id}"
               and x.get("expired") is False and type(x.get("id")) is int
               and x["id"] > 0 and type(x.get("size_in_bytes")) is int
               and 0 < x["size_in_bytes"] <= MAX_ARCHIVE]
    if len(matches) != 1:
        raise ValueError("external Amass artifact absent or ambiguous")
    return matches[0]["id"]


def strict_public_summary(data: dict) -> None:
    """Reject any unexpected field, even nested; no candidates in artifacts."""
    fields = {
        "schema_version", "scanner", "scanner_version", "scan_mode",
        "asset_database", "checked_at", "source_revision", "vantage",
        "status", "scope", "counts", "rejected_count",
        "catalogReconciliation", "finding_semantics",
    }
    cat_fields = {
        "catalogRevision", "catalogEntityCount", "catalogHostnameCount",
        "catalogHostnamesMissingGithubProject", "catalogLanOnlyPolicyConflicts",
        "candidateMatchCounts", "matchedCandidatesMissingGithubProject",
        "semantics", "status",
    }
    matches = {
        "MATCHED_PUBLIC_INTENT", "LAN_ONLY_POLICY_REVIEW",
        "NON_PUBLIC_INTENT_REVIEW", "AMBIGUOUS_ENTITY_REVIEW", "UNMAPPED_REVIEW",
    }
    rec = data.get("catalogReconciliation")
    counts = data.get("counts")
    if (set(data) != fields or not isinstance(rec, dict)
            or set(rec) != cat_fields or not isinstance(counts, dict)
            or not 0 < len(counts) <= 100
            or any(not isinstance(k, str) or not re.fullmatch(r"[a-z0-9.-]{1,253}", k)
                   or type(n) is not int or not 0 <= n <= 1_000_000
                   for k, n in counts.items())
            or not isinstance(data.get("scope"), list)
            or data["scope"] != sorted(counts)
            or not isinstance(rec.get("candidateMatchCounts"), dict)
            or set(rec["candidateMatchCounts"]) != matches
            or any(type(n) is not int or n < 0
                   for n in rec["candidateMatchCounts"].values())
            or sum(rec["candidateMatchCounts"].values()) != sum(counts.values())
            or any(type(rec.get(k)) is not int or rec[k] < 0
                   for k in ("catalogEntityCount", "catalogHostnameCount",
                             "catalogHostnamesMissingGithubProject",
                             "catalogLanOnlyPolicyConflicts",
                             "matchedCandidatesMissingGithubProject"))):
        raise ValueError("external Amass report schema contains unapproved fields")


def unpack(archive: bytes, sha: str) -> bytes:
    if not 0 < len(archive) <= MAX_ARCHIVE:
        raise ValueError("external Amass ZIP oversized")
    try:
        with ZipFile(BytesIO(archive)) as src:
            entries = src.infolist()
            if (len(entries) != 1 or entries[0].filename != TARGET
                    or entries[0].file_size > MAX_REPORT or entries[0].is_dir()
                    or (entries[0].external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("external Amass ZIP has unapproved files")
            content = src.read(TARGET)
    except (BadZipFile, OSError, RuntimeError, KeyError):
        raise ValueError("invalid Amass ZIP") from None
    if not 0 < len(content) <= MAX_REPORT:
        raise ValueError("external Amass report oversized")
    data = json.loads(content)
    if (not isinstance(data, dict) or "candidates" in data
            or "catalogPolicyConflicts" in data
            or data.get("schema_version") != 1 or data.get("scanner") != "amass"
            or data.get("scan_mode") != "active"
            or data.get("status") != "OBSERVED_NOT_CERTIFIED"
            or data.get("vantage") != "external-github-hosted"
            or data.get("source_revision") != sha):
        raise ValueError("external Amass artifact provenance/scope invalid")
    strict_public_summary(data)
    # Later comparison independently verifies exact owned scope and V2 revision.
    return content


def stage(content: bytes, run_id: int, root: Path = PRIVATE_ROOT) -> Path:
    if root.is_symlink():
        raise ValueError("private CTEM dir symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = root.stat()
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o700:
        raise ValueError("private CTEM dir permissions")
    target = root / f"amass-active-{run_id}.json"
    if target.is_symlink():
        raise ValueError("external CTEM report symlink")
    if target.exists():
        st = target.stat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
                or stat.S_IMODE(st.st_mode) != 0o600 or target.read_bytes() != content):
            raise ValueError("existing CTEM artifact differs")
        return target
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
    return target


def run(run_id: int) -> Path:
    token = installation_token(REPO)
    record = metadata(f"repos/{REPO}/actions/runs/{run_id}", token)
    verify_run(record, run_id)
    info = metadata(f"repos/{REPO}/actions/runs/{run_id}/artifacts", token)
    artifact_id = verify_artifact(info.get("artifacts"), run_id)
    content = unpack(api(f"repos/{REPO}/actions/artifacts/{artifact_id}/zip", token),
                     record["head_sha"])
    return stage(content, run_id)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--pull", action="store_true")
    p.add_argument("--run-id", type=int)
    args = p.parse_args()
    if args.check:
        print("CHECK: external active Amass; explicit master workflow run-id required")
        print("CHECK: existing GitHub App Actions:read, counts-only private 0600 file")
        return 0
    if (os.geteuid() != 0 or os.environ.get("CTEM_EXTERNAL_AMASS_PULL_APPROVED") != "YES"
            or not args.run_id or args.run_id < 1):
        p.error("TrueNAS root, approved run and CTEM_EXTERNAL_AMASS_PULL_APPROVED=YES required")
    try:
        path = run(args.run_id)
    except (GitHubArtifactError, ValueError, OSError, RuntimeError, KeyError) as exc:
        label = safe_reason(exc) if isinstance(exc, GitHubArtifactError) else "INVALID_EXTERNAL_AMASS_REPORT"
        raise SystemExit("REJECTED: " + label) from None
    print("ctem_amass_external=STAGED; counts_only=true; file=" + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
