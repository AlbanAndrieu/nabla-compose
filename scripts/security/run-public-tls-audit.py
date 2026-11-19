#!/usr/bin/env python3
"""Bounded testssl.sh evidence projection; never publish raw TLS scan output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

# Reviewed HTTPS frontends only; no scans against shared provider IP ranges.
TARGETS = (
    "www.albanandrieu.com:443",
    "www.bababou.com:443",
    "manager.albandrieu.com:443",
    "truenas.albandrieu.com:7000",
    "famp-albandrieu.albandrieu.com:443",
    "fastapi-sample.fastapicloud.dev:443",
)
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
LEVELS = {"OK", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "WARN", "FATAL"}


def project_report(raw: Path) -> list[dict[str, str]]:
    if not raw.is_file() or raw.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("missing or oversized TLS evidence")
    source = json.loads(raw.read_text(encoding="utf-8"))
    if not isinstance(source, list) or not source:
        raise ValueError("empty or unexpected TLS report")
    findings = []
    for row in source:
        if not isinstance(row, dict):
            raise ValueError("invalid TLS report row")
        code = row.get("id")
        severity = row.get("severity")
        if not (isinstance(code, str) and IDENTIFIER.fullmatch(code)
                and isinstance(severity, str) and severity.upper() in LEVELS):
            raise ValueError("unexpected TLS report metadata")
        findings.append({"id": code, "severity": severity.upper()})
    return findings


def audit(scanner: Path) -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="ctem-tls-") as folder:
        for index, target in enumerate(TARGETS):
            raw = Path(folder) / f"report-{index}.json"
            result = {"target": target, "status": "INCOMPLETE", "findings": [], "error": None}
            try:
                process = subprocess.run(
                    ["bash", str(scanner), "--warnings", "batch", "--color", "0",
                     "-p", "-s", "-P", "-S", "-f", "--jsonfile", str(raw), target],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=180,
                )
                if process.returncode == 0:
                    result["findings"] = project_report(raw)
                    if not any(row["severity"] == "FATAL" for row in result["findings"]):
                        result["status"] = "OBSERVED_NOT_CERTIFIED"
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                result["error"] = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            results.append(result)
    incomplete = any(row["status"] == "INCOMPLETE" for row in results)
    return {"vantage": "external-runner-required",
            "result": "INCOMPLETE" if incomplete else "OBSERVED_NOT_CERTIFIED",
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    scanner = args.scanner.resolve()
    if not scanner.is_file():
        parser.error("testssl.sh missing")
    report = audit(scanner)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"tls_targets={len(report['results'])} result={report['result']}")
    return 3 if report["result"] == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
