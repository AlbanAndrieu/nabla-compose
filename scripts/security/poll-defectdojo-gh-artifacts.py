#!/usr/bin/env python3
"""Poll approved GitHub Actions master runs and stage scans on TrueNAS.

No self-hosted GitHub runner, incoming webhook, public DefectDojo API or gh CLI.
Default: offline dry-run. Optional import requires an independent explicit gate.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))

from github_actions_artifact_api import GitHubArtifactError, metadata  # noqa: E402
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
}
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


def stage(kind: str, run_id: int, source: str = "alban") -> str:
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
    parser.add_argument("--source", choices=["alban", "bababou", "all"], default="alban")
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
            result = stage(kind, run_id, source=source)
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
