#!/usr/bin/env python3
"""Pull a strictly allowlisted master security artifact into a private inbox.

No public DefectDojo URL is used. A separate existing, explicitly approved
import-scan-defectdojo.sh command owns any mutation of DefectDojo.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

REPO = "AlbanAndrieu/nabla-site-alban"
TOKEN_FILE = Path("/mnt/cpool/secrets/runtime/defectdojo/github-read-token")
INBOX = Path("/mnt/cpool/defectdojo/imports/site-alban")
MAX_ZIP_BYTES = 10_000_000
MAX_REPORT_BYTES = 8_000_000
KINDS = {
    "trivy": ("Supply Chain Security (Trivy)", "trivy-security.json", "Trivy Scan"),
    "nuclei": ("Nuclei public DAST (Site Alban)", "nuclei-results/nuclei.jsonl", "Nuclei Scan"),
    "zap": ("Production DAST", "report_json.json", "ZAP Scan"),
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise SystemExit("REJECTED: " + message)


def require_token() -> str:
    if os.geteuid() != 0:
        fail("pull requires root on the private collector")
    if TOKEN_FILE.is_symlink() or not TOKEN_FILE.is_file():
        fail("GitHub read-only token file missing or symlink")
    info = TOKEN_FILE.stat()
    if info.st_uid != 0 or info.st_gid != 0 or (info.st_mode & 0o777) != 0o600:
        fail("token must be root:root mode 0600")
    token = TOKEN_FILE.read_text(encoding="utf8").strip()
    if not token or any(c.isspace() for c in token):
        fail("invalid GitHub artifact read token")
    return token


def api(route: str, token: str) -> bytes:
    if not route.startswith(f"repos/{REPO}/"):
        fail("unsupported API route")
    env = {**os.environ, "GH_TOKEN": token, "GH_PROMPT_DISABLED": "1"}
    try:
        result = subprocess.run(
            ["gh", "api", f"/{route}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=45,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        fail("GitHub API or artifact fetch failed")
    return result.stdout


def metadata(route: str, token: str) -> dict:
    try:
        value = json.loads(api(route, token))
    except (ValueError, UnicodeDecodeError):
        fail("invalid GitHub API JSON")
    if not isinstance(value, dict):
        fail("invalid API object")
    return value


def allowed_artifact(kind: str, run: dict, run_id: int) -> str:
    workflow, _, _ = KINDS[kind]
    if (
        run.get("name") != workflow
        or run.get("head_branch") != "master"
        or run.get("conclusion") != "success"
        or run.get("event") not in {"schedule", "workflow_dispatch", "push"}
        or not isinstance(run.get("head_sha"), str)
        or not SHA_RE.fullmatch(run["head_sha"])
    ):
        fail("run is not a successful trusted master scan")
    if kind == "trivy":
        return "trivy-master-" + run["head_sha"]
    if kind == "nuclei":
        return f"nuclei-public-{run_id}"
    return "zap-production-report"


def filter_findings(kind: str, raw: bytes) -> bytes:
    if len(raw) > MAX_REPORT_BYTES:
        fail("extracted report exceeds private size budget")
    if kind == "nuclei":
        kept: list[str] = []
        for line in raw.decode("utf8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            severity = str(item.get("info", {}).get("severity", "")).lower()
            if severity in {"critical", "high"}:
                kept.append(json.dumps(item, separators=(",", ":")))
        return ("\n".join(kept) + ("\n" if kept else "")).encode()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        fail("invalid report object")
    if kind == "trivy":
        results = payload.get("Results")
        if not isinstance(results, list):
            fail("invalid Trivy results")
        for result in results:
            if not isinstance(result, dict):
                fail("invalid Trivy result")
            result["Vulnerabilities"] = [
                v for v in (result.get("Vulnerabilities") or [])
                if isinstance(v, dict) and str(v.get("Severity", "")).upper() in {"CRITICAL", "HIGH"}
            ]
            # License and configuration reports are reviewed separately, not
            # silently imported as vulnerability findings.
            result.pop("Licenses", None)
            result.pop("Misconfigurations", None)
    elif kind == "zap":
        sites = payload.get("site")
        if not isinstance(sites, list):
            fail("invalid ZAP report")
        for site in sites:
            if not isinstance(site, dict):
                fail("invalid ZAP site")
            site["alerts"] = [
                alert for alert in (site.get("alerts") or [])
                if isinstance(alert, dict) and str(alert.get("riskcode")) == "3"
            ]
    return json.dumps(payload, separators=(",", ":")).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(KINDS), required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--pull", action="store_true", help="fetch and filter; NEVER import automatically")
    args = parser.parse_args()
    if args.run_id <= 0:
        fail("run id must be positive")
    workflow, filename, scan_type = KINDS[args.kind]
    print(f"Policy: {args.kind} -> {scan_type}; source=successful master {workflow}")
    if not args.pull:
        print("CHECK_ONLY: no network, no token, no DefectDojo mutation")
        return

    token = require_token()
    run = metadata(f"repos/{REPO}/actions/runs/{args.run_id}", token)
    artifact_name = allowed_artifact(args.kind, run, args.run_id)
    artifacts = metadata(f"repos/{REPO}/actions/runs/{args.run_id}/artifacts", token)
    matches = [
        a for a in artifacts.get("artifacts", [])
        if a.get("name") == artifact_name and not a.get("expired")
    ]
    if len(matches) != 1:
        fail("required allowlisted master artifact missing or ambiguous")
    artifact = matches[0]
    if not isinstance(artifact.get("id"), int) or not 0 < artifact.get("size_in_bytes", 0) <= MAX_ZIP_BYTES:
        fail("artifact size/id invalid")
    archive = api(f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip", token)
    if len(archive) > MAX_ZIP_BYTES:
        fail("download exceeds zip limit")
    try:
        with ZipFile(BytesIO(archive)) as zipped:
            matching = [m for m in zipped.infolist() if m.filename == filename]
            if len(matching) != 1 or matching[0].file_size > MAX_REPORT_BYTES:
                fail("archive does not contain the expected bounded report")
            raw = zipped.read(matching[0])
        filtered = filter_findings(args.kind, raw)
    except (ValueError, KeyError, UnicodeError, OSError):
        fail("malformed archive or report")
    if not filtered or (
        args.kind == "nuclei" and not filtered.strip()
    ):
        print("NO_ACTIONABLE_FINDINGS: nothing imported")
        return
    if INBOX.is_symlink():
        fail("inbox must not be a symlink")
    INBOX.mkdir(parents=True, exist_ok=True, mode=0o700)
    if INBOX.stat().st_uid != 0 or INBOX.stat().st_mode & 0o077:
        fail("inbox ownership/permissions must be root-only")
    out = INBOX / f"site-alban-{args.run_id}-{args.kind}.json"
    descriptor = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(filtered)
    print(f"READY: restricted report {out}; manually approve import as {scan_type}")


if __name__ == "__main__":
    main()
