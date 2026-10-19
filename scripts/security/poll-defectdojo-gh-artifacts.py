#!/usr/bin/env python3
"""Poll approved GitHub Actions master runs and stage scans on TrueNAS.

No self-hosted GitHub runner, incoming webhook, public DefectDojo API or gh CLI.
Default: offline dry-run. Optional import requires an independent explicit gate.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import re
import stat
from zipfile import ZipFile
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))

from github_actions_artifact_api import GitHubArtifactError, api, metadata  # noqa: E402
from github_app_auth import installation_token  # noqa: E402

PULL = SECURITY / "pull-site-alban-security-report.py"
IMPORT = SECURITY / "import-scan-defectdojo.sh"
REPO = "AlbanAndrieu/nabla-site-alban"
INBOX = Path("/mnt/cpool/defectdojo/imports/site-alban")
SOURCES = {
    "alban": {
        "repository": REPO,
        "workflow_files": {
            "trivy": "security-supply-chain.yml",
            "nuclei": "nuclei-public.yml",
            "zap": "master-dast.yml",
        },
        "workflows": {
            "trivy": ("Supply Chain Security (Trivy)", "Trivy Scan"),
            "nuclei": ("Nuclei public DAST (Site Alban)", "Nuclei Scan"),
            "zap": ("Production DAST", "Zed Attack Proxy"),
        },
    },
    "bababou": {
        "repository": "AlbanAndrieu/nabla-site-bababou",
        "workflow_files": {"zap": "production-dast.yml"},
        "workflows": {"zap": ("Production DAST", "Zed Attack Proxy")},
    },
    # Same TrueNAS collector and GitHub App; repository-specific installation
    # token, inbox and engagement. Opt-in only, not part of default Cron.
    "fastapi-sample": {
        "repository": "AlbanAndrieu/fastapi-sample",
        "workflow_files": {"trivy": "defectdojo-trivy-handoff.yml"},
        "workflows": {"trivy": ("DefectDojo Trivy Handoff (FastAPI)", "Trivy Scan")},
    },
}
FASTAPI_INBOX = Path("/mnt/cpool/defectdojo/imports/fastapi-sample")
FASTAPI_REPORT = "trivy-fastapi-master.json"
FASTAPI_MANIFEST = "trivy-fastapi-master.manifest.json"
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_FIELD = re.compile(r"[A-Za-z0-9._+!-]{1,128}\Z")
_ALLOWED_FIELDS = {"VulnerabilityID", "PkgName", "InstalledVersion", "Severity", "FixedVersion"}


def validate_fastapi_handoff(run: dict, manifest: bytes, report: bytes) -> bool:
    """Deny arbitrary SARIF, secrets, source snippets and other Trivy targets."""
    if len(manifest) > 8192 or len(report) > 1_000_000:
        fail("fastapi handoff exceeds the private collection budget")
    try:
        meta = json.loads(manifest)
        payload = json.loads(report)
    except (UnicodeError, ValueError):
        fail("invalid fastapi artifact payload")
    if not isinstance(meta, dict) or not isinstance(payload, dict):
        fail("invalid fastapi artifact schema")
    if (meta.get("schema_version") != 1 or meta.get("project") != "fastapi-sample"
            or meta.get("scope") != "uv.lock-only-high-critical"
            or meta.get("mode") != "master" or meta.get("state") != "complete"
            or meta.get("scanner") != "Trivy Scan"
            or meta.get("policy_status") not in {"pass", "needs_review"}
            or meta.get("revision") != run.get("head_sha")
            or _SHA40.fullmatch(str(meta.get("revision"))) is None
            or _SHA256.fullmatch(str(meta.get("source_report_sha256"))) is None
            or meta.get("report_file") != FASTAPI_REPORT
            or meta.get("artifact_sha256") != sha256(report).hexdigest()):
        fail("fastapi artifact provenance or digest mismatch")
    counts = {"HIGH": 0, "CRITICAL": 0}
    if set(payload) != {"SchemaVersion", "Results"} or payload["SchemaVersion"] != 2:
        fail("fastapi Trivy output has unapproved fields")
    rows = payload["Results"]
    if not isinstance(rows, list) or len(rows) > 1:
        fail("invalid fastapi Trivy result count")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"Target", "Class", "Type", "Vulnerabilities"}:
            fail("unexpected Trivy result fields")
        if row["Target"] != "uv.lock" or row["Class"] != "lang-pkgs" or row["Type"] != "python-pkg":
            fail("unauthorized Trivy target")
        findings = row["Vulnerabilities"]
        if not isinstance(findings, list) or len(findings) > 1000:
            fail("invalid Trivy finding count")
        for finding in findings:
            if not isinstance(finding, dict) or not {"VulnerabilityID", "PkgName", "InstalledVersion", "Severity"}.issubset(finding) or set(finding) - _ALLOWED_FIELDS:
                fail("unapproved Trivy findings")
            if finding["Severity"] not in counts:
                fail("unapproved Trivy severity")
            if any(not isinstance(v, str) or not _SAFE_FIELD.fullmatch(v) for k, v in finding.items() if k != "Severity"):
                fail("unsafe Trivy field")
            counts[finding["Severity"]] += 1
    if meta.get("counts") != counts:
        fail("fastapi handoff counts do not match findings")
    if counts["CRITICAL"] and meta.get("policy_status") != "needs_review":
        fail("Critical findings cannot report PASS")
    if not counts["CRITICAL"] and meta.get("policy_status") == "needs_review":
        fail("contradictory fastapi scan status")
    return bool(counts["CRITICAL"] or counts["HIGH"])


def stage_fastapi_handoff(token: str, run_id: int) -> str:
    """Collect a strictly bounded handoff through the SAME shared poller."""
    repo = SOURCES["fastapi-sample"]["repository"]
    run = metadata(f"repos/{repo}/actions/runs/{run_id}", token)
    if (run.get("id") != run_id or run.get("name") != SOURCES["fastapi-sample"]["workflows"]["trivy"][0]
            or run.get("head_branch") != "master" or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("event") not in {"workflow_dispatch", "push", "schedule"}
            or _SHA40.fullmatch(str(run.get("head_sha"))) is None):
        fail("fastapi source run is not an approved completed master scan")
    artifact_name = "defectdojo-fastapi-trivy-" + run["head_sha"]
    listing = metadata(f"repos/{repo}/actions/runs/{run_id}/artifacts", token)
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
        fail("invalid GitHub artifacts metadata")
    matches = [row for row in artifacts if isinstance(row, dict)
               and row.get("name") == artifact_name and row.get("expired") is False
               and type(row.get("id")) is int and row["id"] > 0
               and type(row.get("size_in_bytes")) is int
               and 0 < row["size_in_bytes"] <= 10_000_000]
    if len(matches) != 1:
        fail("missing or ambiguous fastapi artifact")
    archive = api(f"repos/{repo}/actions/artifacts/{matches[0]['id']}/zip", token)
    try:
        with ZipFile(BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if {x.filename for x in entries} != {FASTAPI_REPORT, FASTAPI_MANIFEST} or len(entries) != 2:
                fail("unexpected fastapi ZIP content")
            if any(x.is_dir() or (x.external_attr >> 16) & 0o170000 == 0o120000
                   or x.file_size > 1_000_000 or x.compress_size > 10_000_000
                   for x in entries):
                fail("unsafe fastapi ZIP member")
            report = zipped.read(FASTAPI_REPORT)
            manifest = zipped.read(FASTAPI_MANIFEST)
    except (OSError, ValueError, RuntimeError, KeyError):
        fail("fastapi artifact ZIP is not valid")
    if not validate_fastapi_handoff(run, manifest, report):
        return "NO_ACTIONABLE_FINDINGS"
    if FASTAPI_INBOX.is_symlink():
        fail("fastapi inbox cannot be a symlink")
    FASTAPI_INBOX.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = FASTAPI_INBOX.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        fail("fastapi inbox permissions must be private")
    out = FASTAPI_INBOX / f"fastapi-{run_id}-trivy.json"
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if out.is_symlink() or not out.is_file() or out.stat().st_mode & 0o077:
            fail("existing fastapi artifact is unsafe")
        return "ALREADY_STAGED"
    with os.fdopen(fd, "wb") as stream:
        stream.write(report)
    return "STAGED"


WORKFLOW_FILES = {
    "trivy": "security-supply-chain.yml",
    "nuclei": "nuclei-public.yml",
    "zap": "master-dast.yml",
}
WORKFLOWS = {
    "trivy": ("Supply Chain Security (Trivy)", "Trivy Scan"),
    "nuclei": ("Nuclei public DAST (Site Alban)", "Nuclei Scan"),
    "zap": ("Production DAST", "Zed Attack Proxy"),
}


def fail(message: str) -> None:
    raise SystemExit("REJECTED: " + message)


def latest_runs(token: str, source: str = "alban") -> dict[str, int]:
    """Select latest completed successful master run for each exact workflow.

    Never backtrack to an older successful run when a newer scan failed.
    Per-workflow pagination avoids losing infrequent scans among other CI runs.
    """
    config = SOURCES[source]
    selected: dict[str, int] = {}
    for kind, (workflow, _) in config["workflows"].items():
        name = config["workflow_files"][kind]
        route = f"repos/{config['repository']}/actions/workflows/{name}/runs?branch=master&per_page=10"
        runs = metadata(route, token).get("workflow_runs", [])
        if not isinstance(runs, list) or len(runs) > 10:
            fail("invalid bounded workflow list")
        matching = [
            entry for entry in runs
            if isinstance(entry, dict)
            and entry.get("name") == workflow
            and entry.get("head_branch") == "master"
            and entry.get("event") in {"schedule", "workflow_dispatch", "push"}
            and isinstance(entry.get("id"), int)
            and entry["id"] > 0
            and isinstance(entry.get("head_sha"), str)
            and len(entry["head_sha"]) == 40
            and all(ch in "0123456789abcdef" for ch in entry["head_sha"])
        ]
        if matching:
            latest = max(matching, key=lambda entry: entry["id"])
            if latest.get("conclusion") == "success" and latest.get("status") == "completed":
                selected[kind] = latest["id"]
            # A failed, pending, or cancelled latest scan blocks stale imports.
    return selected


def stage(kind: str, run_id: int, source: str = "alban", token: str = "") -> str:
    if source == "fastapi-sample":
        if kind != "trivy" or not token:
            fail("fastapi handoff requires an approved scoped token")
        return stage_fastapi_handoff(token, run_id)
    # The downloaded ZIP and JSON are validated again by the restricted collector.
    suffix = "xml" if kind == "zap" else "json"
    output = Path("/mnt/cpool/defectdojo/imports") / f"site-{source}" / f"site-{source}-{run_id}-{kind}.{suffix}"
    if output.exists():
        if output.is_symlink() or not output.is_file():
            fail("staged report path is unsafe")
        return "ALREADY_STAGED"
    result = subprocess.run(
        [sys.executable, str(PULL), "--kind", kind, "--run-id", str(run_id), "--pull"],
        capture_output=True, text=True, check=False, timeout=150,
    )
    if result.returncode:
        fail("one approved scan could not be staged; private details suppressed")
    if output.is_file() and not output.is_symlink():
        return "STAGED"
    return "NO_FINDINGS_OR_MISSING"


def import_report(kind: str, run_id: int, source: str = "alban") -> None:
    if os.environ.get("DEFECTDOJO_IMPORT_APPROVED") != "YES":
        fail("import requires DEFECTDOJO_IMPORT_APPROVED=YES")
    engagement = os.environ.get(f"DEFECTDOJO_SITE_{source.upper()}_ENGAGEMENT_ID", "")
    if not engagement.isascii() or not engagement.isdecimal() or not int(engagement):
        fail("approved DefectDojo site-alban engagement ID missing")
    suffix = "xml" if kind == "zap" else "json"
    output = Path("/mnt/cpool/defectdojo/imports") / f"site-{source}" / f"site-{source}-{run_id}-{kind}.{suffix}"
    env = {
        **os.environ,
        "DEFECTDOJO_SERVICE_ID": f"nabla-site-{source}",
        "DEFECTDOJO_SCAN_TYPE": SOURCES[source]["workflows"][kind][1],
        "DEFECTDOJO_ENGAGEMENT_ID": engagement,
    }
    result = subprocess.run(
        ["bash", str(IMPORT), "--apply", str(output)],
        check=False, capture_output=True, text=True, timeout=120, env=env,
    )
    if result.returncode:
        fail("DefectDojo reimport failed; response and secret contents suppressed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--pull", action="store_true")
    group.add_argument("--pull-and-import", action="store_true")
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="alban")
    parser.add_argument("--kind", choices=["all", *WORKFLOWS], default="all")
    args = parser.parse_args()
    requested = SOURCES if args.source == "all" else {args.source: SOURCES[args.source]}
    if args.kind != "all" and not any(args.kind in entry["workflows"] for entry in requested.values()):
        fail("scan kind is not configured for the selected sources")
    if args.check:
        print("CHECK: approved master GitHub Actions workflows; no token or LAN access")
        print("CHECK: " + ", ".join(f"{name}:{','.join(cfg['workflows'])}" for name, cfg in requested.items()))
        return 0
    if "fastapi-sample" in requested and os.environ.get("DEFECTDOJO_FASTAPI_PULL_APPROVED") != "YES":
        fail("fastapi source requires explicit local opt-in before artifact polling")
    if args.pull_and_import and "fastapi-sample" in requested:
        fail("fastapi import needs a separately accepted parser and engagement; only --pull allowed")
    if os.geteuid() != 0 or not Path("/mnt/cpool/compose/nabla-compose").is_dir():
        fail("polling restricted to canonical TrueNAS host")
    if args.pull_and_import and os.environ.get("DEFECTDOJO_IMPORT_APPROVED") != "YES":
        fail("explicit import approval required")
    for source, config in requested.items():
        kinds = config["workflows"] if args.kind == "all" else (
            {args.kind: config["workflows"][args.kind]}
            if args.kind in config["workflows"] else {}
        )
        if not kinds:
            continue
        token = installation_token(config["repository"])
        runs = latest_runs(token, source=source)
        for kind in kinds:
            run_id = runs.get(kind)
            if run_id is None:
                print(f"NOT_OBSERVED: {source}/{kind} has no approved latest successful master run")
                continue
            result = stage(kind, run_id, source=source, token=token)
            print(f"{source}/{kind}: {result}; run_id={run_id}; import=not_attempted")
            if result == "STAGED" and args.pull_and_import:
                import_report(kind, run_id, source=source)
                print(f"{source}/{kind}: import_acknowledged; async parser acceptance required")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GitHubArtifactError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit("REJECTED: artifact collector failure; no credentials disclosed") from None
