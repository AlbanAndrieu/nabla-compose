#!/usr/bin/env python3
"""Project reviewed checkdmarc anomalies to DefectDojo Generic Findings Import.

No raw DNS records, candidate names, tokens or automatic API calls.
The input is the minimized public-mail-deep JSON, not checkdmarc raw JSON.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIL_SCOPE = ROOT / "config/security/public-mail-domains.json"
CONTROLS = {
    "spf_valid": ("Invalid SPF configuration", "Medium"),
    "dmarc_valid": ("Invalid DMARC configuration", "Medium"),
}
DMARC_NONE = "DMARC policy does not enforce rejection"


def project(data: dict, domains: set[str], now: datetime | None = None) -> dict:
    mail = data.get("checkdmarc")
    if not isinstance(mail, dict) or mail.get("status") != "OBSERVED_NOT_CERTIFIED":
        raise ValueError("checkdmarc evidence not complete")
    timestamp = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or not timedelta(0) <= current - timestamp <= timedelta(days=14):
        raise ValueError("checkdmarc evidence not fresh")
    if set(data.get("scope", [])) != domains:
        raise ValueError("checkdmarc reviewed domain scope mismatch")
    rows = mail.get("results")
    if not isinstance(rows, list) or len(rows) != len(domains):
        raise ValueError("incomplete checkdmarc domain results")
    seen = set()
    findings = []
    for row in rows:
        if not isinstance(row, dict) or row.get("domain") not in domains:
            raise ValueError("unreviewed mail domain")
        domain = row["domain"]
        if domain in seen:
            raise ValueError("duplicate checkdmarc domain")
        seen.add(domain)
        problems = []
        for field, (title, severity) in CONTROLS.items():
            if row.get(field) is False:
                problems.append((field, title, severity))
        if row.get("dmarc_valid") is True and row.get("dmarc_p") == "none":
            problems.append(("dmarc_p", DMARC_NONE, "Medium"))
        for key, title, severity in problems:
            unique = hashlib.sha256(f"ctem-mail|{domain}|{key}".encode()).hexdigest()
            findings.append({
                "title": title + " (" + domain + ")",
                "severity": severity,
                "description": (
                    "Reviewed checkdmarc policy anomaly: " + key
                    + " for the authorized domain " + domain
                    + ". Verify DNS and sending services before remediation."
                ),
                "unique_id_from_tool": "ctem-mail-" + unique,
                "active": True,
                "verified": False,
            })
    if seen != domains:
        raise ValueError("missing checkdmarc domain")
    return {
        "name": "Nabla CTEM mail authentication",
        "type": "CTEM Mail Policy",
        "findings": findings,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reviewed", action="store_true",
                   help="explicit human review of the source report")
    args = p.parse_args()
    if not args.reviewed:
        p.error("--reviewed is required before staging DefectDojo findings")
    src = args.input
    if src.is_symlink() or not src.is_file() or src.stat().st_size > 2_000_000:
        p.error("expected bounded regular report")
    domains = {row["name"] for row in json.loads(MAIL_SCOPE.read_text())["domains"]}
    report = project(json.loads(src.read_text()), domains)
    if not report["findings"]:
        print("CTEM mail: no actionable reviewed findings; no DefectDojo upload")
        return 0
    output = args.output
    if not output.is_absolute() or not output.parent.is_dir():
        p.error("private absolute output path required")
    fd = None
    import os
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            fd = None
            json.dump(report, out, indent=2)
            out.write("\n")
    finally:
        if fd is not None:
            os.close(fd)
    print(f"CTEM mail: staged {len(report['findings'])} reviewed findings privately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
