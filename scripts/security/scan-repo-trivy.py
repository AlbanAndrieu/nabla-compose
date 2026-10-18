#!/usr/bin/env python3
"""Generate a private Trivy SCA report for this repository; never upload it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = "/mnt/cpool/security/scans"


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only contract check (default)")
    parser.add_argument("--scan", action="store_true", help="explicit private Trivy SCA scan")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    if not args.scan:
        print("READY: repo=nabla-compose parser=Trivy Scan network=false upload=false")
        return 0

    if os.environ.get("NABLA_DEFECTDOJO_SCAN_APPROVED") != "YES":
        print("ERROR: explicit scan approval required", file=sys.stderr)
        return 2
    if os.geteuid() == 0:
        print("ERROR: run scanner without root", file=sys.stderr)
        return 2

    directory = Path(args.report_dir)
    if (not directory.is_absolute() or directory.is_symlink()
            or not directory.is_dir() or directory.stat().st_mode & 0o777 != 0o700):
        print("ERROR: private 0700 report directory required", file=sys.stderr)
        return 2
    if not os.access(directory, os.W_OK):
        return 2
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    if tracked.stdout:
        print("ERROR: tracked source must be clean", file=sys.stderr)
        return 2
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return 2

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = directory / f"nabla-compose-{revision}-{timestamp}.trivy.json"
    if report.exists():
        return 2
    fd, temp_name = tempfile.mkstemp(prefix=".trivy-", dir=directory)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        # Avoid scanning ignored .env files, untracked documents or live datasets.
        # Scan a sandboxed archive containing only tracked HEAD content.
        with tempfile.TemporaryDirectory(prefix=".trivy-source-", dir=directory) as snapshot:
            with subprocess.Popen(
                ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            ) as archive:
                if archive.stdout is None:
                    raise ValueError("git archive has no output stream")
                with tarfile.open(fileobj=archive.stdout, mode="r|") as entries:
                    entries.extractall(path=snapshot, filter="data")
                if archive.wait(timeout=30) != 0:
                    raise ValueError("git archive failed")
            subprocess.run(
                [
                    "trivy", "fs", "--quiet", "--scanners", "vuln",
                    "--format", "json", "--output", str(temporary),
                    "--skip-dirs", str(Path(snapshot) / "node_modules"),
                    str(snapshot),
                ],
                check=True, timeout=600,
            )
        payload = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("Results"), list):
            raise ValueError("invalid Trivy JSON: missing Results")
        if not 0 < temporary.stat().st_size <= 10_000_000:
            raise ValueError("report exceeds existing DefectDojo importer limit")
        temporary.chmod(0o600)
        temporary.replace(report)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("ERROR: Trivy failed or report validation failed", file=sys.stderr)
        return 1
    finally:
        temporary.unlink(missing_ok=True)
    print(f"CREATED: {report.name}; private=true upload=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
