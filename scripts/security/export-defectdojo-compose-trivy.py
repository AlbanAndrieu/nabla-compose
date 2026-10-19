#!/usr/bin/env python3
"""Produce reviewed Trivy JSON + provenance manifest for master artifact handoff.

Reads an existing Trivy fs result. Never packages raw source, secrets, licenses,
SBOM, misconfig evidence or arbitrary URLs. No DefectDojo/network access.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

FIELDS = frozenset({"VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity"})
REQUIRED = frozenset({"VulnerabilityID", "PkgName", "Severity"})
SAFE_FIELD = re.compile(r"[A-Za-z0-9_.:+!@/-]{1,128}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
LOCK = re.compile(
    r"(?:[A-Za-z0-9._-]+/)*(?:uv[.]lock|poetry[.]lock|Pipfile[.]lock|"
    r"package-lock[.]json|pnpm-lock[.]yaml|requirements[A-Za-z0-9._-]*[.]txt)\Z"
)
MAX_BYTES = 10_000_000
MAX_ROWS = 120


def sanitize(payload: object) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("Results"), list):
        raise ValueError("Trivy Results array required")
    out = []
    for row in payload["Results"]:
        if not isinstance(row, dict):
            raise ValueError("invalid scanner row")
        target = row.get("Target")
        if not isinstance(target, str) or not LOCK.fullmatch(target):
            continue
        if row.get("Class") not in ("lang-pkgs", "os-pkgs", None):
            continue
        findings = []
        for item in row.get("Vulnerabilities") or []:
            if not isinstance(item, dict):
                raise ValueError("invalid finding")
            if item.get("Severity") not in ("HIGH", "CRITICAL"):
                continue
            minimal = {k: v for k, v in item.items() if k in FIELDS}
            if not REQUIRED.issubset(minimal) or any(
                not isinstance(v, str) or not SAFE_FIELD.fullmatch(v)
                for v in minimal.values()
            ):
                raise ValueError("unsafe finding metadata")
            findings.append(minimal)
        if findings:
            out.append({
                "Target": target.split("/")[-1],
                "Class": "lang-pkgs",
                "Type": row.get("Type") if row.get("Type") in ("npm", "pip", "poetry", "pnpm", "python-pkg") else "unknown",
                "Vulnerabilities": findings,
            })
        if len(out) > MAX_ROWS:
            raise ValueError("too many lockfile results")
    return {"SchemaVersion": 2, "Results": out}


def produce(source: Path, output: Path, manifest: Path, revision: str) -> None:
    if not SHA.fullmatch(revision):
        raise ValueError("40-character immutable git revision required")
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError("scanner input missing or exceeds limit")
    if output.exists() or manifest.exists():
        raise ValueError("output exists; refusing overwrite")
    minimal = sanitize(json.loads(source.read_text(encoding="utf-8")))
    report = (json.dumps(minimal, sort_keys=True, separators=(",", ":")) + "\n").encode()
    counts = {"HIGH": 0, "CRITICAL": 0}
    for row in minimal["Results"]:
        for finding in row["Vulnerabilities"]:
            counts[finding["Severity"]] += 1
    meta = {
        "schema_version": 1,
        "project": "nabla-compose",
        "scanner": "Trivy Scan",
        "mode": "master",
        "state": "complete",
        "revision": revision,
        "report_file": "trivy-compose-master.json",
        "report_sha256": sha256(report).hexdigest(),
        "counts": counts,
    }
    output.write_bytes(report)
    manifest.write_text(json.dumps(meta, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--revision", required=True)
    args = p.parse_args()
    produce(args.input, args.report, args.manifest, args.revision)
    print("PASS: minimal lockfile HIGH/CRITICAL handoff generated without raw evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
