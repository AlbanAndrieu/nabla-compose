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
from zipfile import BadZipFile, ZipFile
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
            "zap": ("Production DAST", "ZAP Scan"),
        },
    },
    "bababou": {
        "repository": "AlbanAndrieu/nabla-site-bababou",
        "workflow_files": {"zap": "production-dast.yml"},
        "workflows": {"zap": ("Production DAST", "ZAP Scan")},
    },
    # Same TrueNAS collector and GitHub App; repository-specific installation
    # token, inbox and engagement. Opt-in only, not part of default Cron.
    "compose": {
        "repository": "AlbanAndrieu/nabla-compose",
        "workflow_files": {"trivy": "defectdojo-compose-handoff.yml"},
        "workflows": {"trivy": ("DefectDojo Compose Trivy Handoff", "Trivy Scan")},
    },
    "fastapi-sample": {
        "repository": "AlbanAndrieu/fastapi-sample",
        "workflow_files": {"trivy": "docker-build.yml"},
        "workflows": {"trivy": ("Docker CI", "Trivy Scan")},
    },
}
FASTAPI_INBOX = Path("/mnt/cpool/defectdojo/imports/fastapi-sample")
FASTAPI_REPORT = "trivy-results.json"
_SHA40 = re.compile(r"[0-9a-f]{40}\\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\\Z")


def validate_fastapi_handoff(report: bytes) -> bool:
    """Validate native Trivy JSON without transforming findings for DefectDojo.

    Reject secret/config evidence at the transport boundary. GitHub Actions
    must produce a vulnerability-only image scan, never a host/LAN scan.
    """
    if not 0 < len(report) <= 8_000_000:
        fail("native Trivy report outside allowed size")
    try:
        value = json.loads(report)
    except (ValueError, UnicodeError):
        fail("malformed native Trivy JSON")
    if (not isinstance(value, dict)
            or value.get("SchemaVersion") != 2
            or not isinstance(value.get("Results"), list)
            or len(value["Results"]) > 1000):
        fail("unexpected native Trivy schema")
    actionable = False
    for result in value["Results"]:
        if not isinstance(result, dict):
            fail("invalid native Trivy result")
        if result.get("Secrets") or result.get("Misconfigurations"):
            fail("secret/config evidence not permitted in GitHub artifact")
        findings = result.get("Vulnerabilities") or []
        if not isinstance(findings, list) or len(findings) > 5000:
            fail("invalid Trivy vulnerabilities")
        for finding in findings:
            if not isinstance(finding, dict) or not isinstance(finding.get("VulnerabilityID"), str):
                fail("invalid native Trivy vulnerability")
            actionable = True
    return actionable


COMPOSE_REPORT = "trivy-compose-master.json"
COMPOSE_MANIFEST = "trivy-compose-master.manifest.json"
COMPOSE_INBOX = Path("/mnt/cpool/defectdojo/imports/nabla-compose")


def validate_compose_handoff(run: dict, manifest: bytes, report: bytes) -> bool:
    """Check SHA-bound provenance and a minimal lockfile-only report."""
    if len(manifest) > 8192 or len(report) > 1_000_000:
        fail("compose report exceeds private budget")
    try:
        meta = json.loads(manifest)
        payload = json.loads(report)
    except (ValueError, UnicodeError):
        fail("invalid compose handoff JSON")
    if not isinstance(meta, dict) or not isinstance(payload, dict):
        fail("invalid compose artifact schema")
    if (set(meta) != {"schema_version", "project", "scanner", "mode", "state",
                      "revision", "report_file", "report_sha256", "counts"}
            or meta.get("schema_version") != 1
            or meta.get("project") != "nabla-compose"
            or meta.get("scanner") != "Trivy Scan"
            or meta.get("mode") != "master" or meta.get("state") != "complete"
            or meta.get("revision") != run.get("head_sha")
            or _SHA40.fullmatch(str(meta.get("revision"))) is None
            or meta.get("report_file") != COMPOSE_REPORT
            or meta.get("report_sha256") != sha256(report).hexdigest()):
        fail("compose artifact digest or origin mismatch")
    spec = importlib.util.spec_from_file_location(
        "compose_handoff", SECURITY / "export-defectdojo-compose-trivy.py"
    )
    if spec is None or spec.loader is None:
        fail("missing reviewed compose sanitizer")
    sanitizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sanitizer)
    if sanitizer.sanitize(payload) != payload:
        fail("compose Trivy report contains unauthorized evidence")
    counts = {"HIGH": 0, "CRITICAL": 0}
    for row in payload["Results"]:
        for finding in row["Vulnerabilities"]:
            counts[finding["Severity"]] += 1
    if meta["counts"] != counts:
        fail("compose finding counts mismatch")
    return sum(counts.values()) > 0


def stage_compose_handoff(token: str, run_id: int) -> str:
    """Stage exactly two reviewed ZIP members from an immutable master run."""
    repo = SOURCES["compose"]["repository"]
    run = metadata(f"repos/{repo}/actions/runs/{run_id}", token)
    if (run.get("id") != run_id or run.get("name") != "DefectDojo Compose Trivy Handoff"
            or run.get("head_branch") != "master" or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("event") not in {"schedule", "workflow_dispatch"}
            or _SHA40.fullmatch(str(run.get("head_sha"))) is None):
        fail("compose artifact run provenance invalid")
    artifact_name = "defectdojo-compose-trivy-" + run["head_sha"]
    listing = metadata(f"repos/{repo}/actions/runs/{run_id}/artifacts", token)
    matches = [
        a for a in listing.get("artifacts", [])
        if isinstance(a, dict) and a.get("name") == artifact_name
        and a.get("expired") is False
        and type(a.get("id")) is int and a["id"] > 0
        and type(a.get("size_in_bytes")) is int
        and 0 < a["size_in_bytes"] <= 10_000_000
    ]
    if len(matches) != 1:
        fail("compose artifact absent or ambiguous")
    archive = api(f"repos/{repo}/actions/artifacts/{matches[0]['id']}/zip", token)
    try:
        with ZipFile(BytesIO(archive)) as z:
            entries = z.infolist()
            if len(entries) != 2 or {x.filename for x in entries} != {
                COMPOSE_REPORT, COMPOSE_MANIFEST
            }:
                fail("unapproved compose archive entries")
            if any(x.is_dir() or (x.external_attr >> 16) & 0o170000 == 0o120000
                   or x.file_size > 1_000_000 for x in entries):
                fail("unsafe compose archive")
            report, manifest = z.read(COMPOSE_REPORT), z.read(COMPOSE_MANIFEST)
    except (OSError, BadZipFile, KeyError, RuntimeError, ValueError):
        fail("compose ZIP invalid")
    if not validate_compose_handoff(run, manifest, report):
        return "NO_ACTIONABLE_FINDINGS"
    if COMPOSE_INBOX.is_symlink():
        fail("compose inbox symlink forbidden")
    COMPOSE_INBOX.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = COMPOSE_INBOX.stat()
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        fail("compose inbox not private")
    target = COMPOSE_INBOX / f"compose-{run_id}-trivy.json"
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if target.is_symlink() or not target.is_file() or target.stat().st_mode & 0o077:
            fail("unsafe staged compose report")
        return "ALREADY_STAGED"
    with os.fdopen(fd, "wb") as stream:
        stream.write(report)
    return "STAGED"


def stage_fastapi_handoff(token: str, run_id: int) -> str:
    """Stage native Trivy JSON from the already-scheduled Docker CI scan."""
    repo = SOURCES["fastapi-sample"]["repository"]
    run = metadata(f"repos/{repo}/actions/runs/{run_id}", token)
    if (run.get("id") != run_id or run.get("name") != "Docker CI"
            or run.get("head_branch") != "master" or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("event") not in {"schedule", "workflow_dispatch"}
            or _SHA40.fullmatch(str(run.get("head_sha"))) is None):
        fail("FastAPI scan run provenance rejected")
    artifact_name = "defectdojo-fastapi-trivy-" + run["head_sha"]
    listing = metadata(f"repos/{repo}/actions/runs/{run_id}/artifacts", token)
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
        fail("invalid FastAPI artifact listing")
    matching = [
        item for item in artifacts if isinstance(item, dict)
        and item.get("name") == artifact_name and item.get("expired") is False
        and type(item.get("id")) is int and item["id"] > 0
        and type(item.get("size_in_bytes")) is int
        and 0 < item["size_in_bytes"] <= 10_000_000
    ]
    if len(matching) != 1:
        fail("FastAPI native Trivy artifact absent or ambiguous")
    archive = api(f"repos/{repo}/actions/artifacts/{matching[0]['id']}/zip", token)
    try:
        with ZipFile(BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if len(entries) != 1 or entries[0].filename != FASTAPI_REPORT:
                fail("FastAPI archive members not allowlisted")
            item = entries[0]
            if (item.is_dir() or ((item.external_attr >> 16) & 0o170000) == 0o120000
                    or item.file_size > 8_000_000 or item.compress_size > 10_000_000):
                fail("FastAPI artifact ZIP member is unsafe")
            report = zipped.read(FASTAPI_REPORT)
    except (OSError, BadZipFile, ValueError, RuntimeError, KeyError):
        fail("FastAPI native Trivy archive invalid")
    if not validate_fastapi_handoff(report):
        return "NO_ACTIONABLE_FINDINGS"
    if FASTAPI_INBOX.is_symlink():
        fail("FastAPI inbox symlink forbidden")
    FASTAPI_INBOX.mkdir(parents=True, mode=0o700, exist_ok=True)
    meta = FASTAPI_INBOX.stat()
    if meta.st_uid != os.geteuid() or meta.st_mode & 0o077:
        fail("FastAPI inbox not private")
    out = FASTAPI_INBOX / f"fastapi-{run_id}-trivy.json"
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if out.is_symlink() or not out.is_file() or out.stat().st_mode & 0o077:
            fail("existing FastAPI artifact unsafe")
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
    "zap": ("Production DAST", "ZAP Scan"),
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
    if source in {"fastapi-sample", "compose"}:
        if kind != "trivy" or not token:
            fail("lockfile handoff requires an approved scoped token")
        if source == "compose":
            return stage_compose_handoff(token, run_id)
        return stage_fastapi_handoff(token, run_id)
    # The downloaded ZIP and JSON are validated again by the restricted collector.
    suffix = "xml" if kind == "zap" else "json"
    output = (
        COMPOSE_INBOX / f"compose-{run_id}-trivy.json"
        if source == "compose"
        else FASTAPI_INBOX / f"fastapi-{run_id}-trivy.json"
        if source == "fastapi-sample"
        else Path("/mnt/cpool/defectdojo/imports") / f"site-{source}"
             / f"site-{source}-{run_id}-{kind}.{suffix}"
    )
    if output.exists():
        if output.is_symlink() or not output.is_file():
            fail("staged report path is unsafe")
        return "ALREADY_STAGED"
    result = subprocess.run(
        [sys.executable, str(PULL), "--source", source, "--kind", kind, "--run-id", str(run_id), "--pull"],
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
    prefix = {"compose": "COMPOSE", "fastapi-sample": "FASTAPI_SAMPLE",
              "alban": "SITE_ALBAN", "bababou": "SITE_BABABOU"}[source]
    engagement = os.environ.get(f"DEFECTDOJO_{prefix}_ENGAGEMENT_ID", "")
    if not engagement.isascii() or not engagement.isdecimal() or not int(engagement):
        fail("approved DefectDojo site-alban engagement ID missing")
    suffix = "xml" if kind == "zap" else "json"
    output = (
        COMPOSE_INBOX / f"compose-{run_id}-trivy.json"
        if source == "compose"
        else FASTAPI_INBOX / f"fastapi-{run_id}-trivy.json"
        if source == "fastapi-sample"
        else Path("/mnt/cpool/defectdojo/imports") / f"site-{source}"
             / f"site-{source}-{run_id}-{kind}.{suffix}"
    )
    env = {
        **os.environ,
        "DEFECTDOJO_SERVICE_ID": (
            "nabla-compose" if source == "compose"
            else "fastapi-sample" if source == "fastapi-sample"
            else f"nabla-site-{source}"
        ),
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
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    parser.add_argument("--kind", choices=["all", *WORKFLOWS], default="all")
    args = parser.parse_args()
    requested = SOURCES if args.source == "all" else {args.source: SOURCES[args.source]}
    if args.kind != "all" and not any(args.kind in entry["workflows"] for entry in requested.values()):
        fail("scan kind is not configured for the selected sources")
    if args.check:
        print("CHECK: approved master GitHub Actions workflows; no token or LAN access")
        print("CHECK: " + ", ".join(f"{name}:{','.join(cfg['workflows'])}" for name, cfg in requested.items()))
        return 0
    if os.geteuid() != 0 or not Path("/mnt/cpool/compose/nabla-compose").is_dir():
        fail("polling restricted to canonical TrueNAS host")
    if args.pull_and_import and os.environ.get("DEFECTDOJO_IMPORT_APPROVED") != "YES":
        fail("explicit import approval required")
    for source, config in requested.items():
        if (source == "fastapi-sample" and args.pull_and_import
                and os.environ.get("DEFECTDOJO_FASTAPI_IMPORT_APPROVED") != "YES"):
            if args.source == "fastapi-sample":
                fail("fastapi import requires separate parser/engagement acceptance")
            print("NOT_APPROVED: fastapi-sample import requires explicit authorization")
            continue
        if source == "fastapi-sample" and os.environ.get("DEFECTDOJO_FASTAPI_PULL_APPROVED") != "YES":
            if args.source == "fastapi-sample":
                fail("fastapi source requires explicit opt-in")
            print("NOT_APPROVED: fastapi-sample requires local pull authorization")
            continue
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
