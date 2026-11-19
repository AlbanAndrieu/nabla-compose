#!/usr/bin/env python3
"""Independent checkdmarc/Nuclei DNS audit. No raw records in published reports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ("dmarc-detect", "spf-record-detect", "spf-limit-lookup")
DKIM = "ctem-dkim-published"
LEVELS = {"info", "low", "medium", "high", "critical"}


def load_scope(config: Path):
    scope = runpy.run_path(str(ROOT / "scripts/security/check-public-mail-auth.py"))
    rows = scope["read_scope"](config)
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("duplicate mail domain")
    return rows


def execute(command: list[str], timeout: int) -> bool:
    try:
        return subprocess.run(command, timeout=timeout, check=False,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def read_report(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("missing or oversized evidence")
    return path.read_text(encoding="utf-8")


def project_checkdmarc(raw: Path, domains: set[str]) -> list[dict]:
    data = json.loads(read_report(raw))
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("invalid checkdmarc report")
    result = []
    seen = set()
    for item in data:
        if not isinstance(item, dict) or item.get("domain") not in domains:
            raise ValueError("unexpected domain")
        domain = item["domain"]
        if domain in seen:
            raise ValueError("duplicate result")
        seen.add(domain)
        row = {"domain": domain}
        for name in ("spf", "dmarc", "mta_sts", "smtp_tls_reporting"):
            check = item.get(name)
            value = check.get("valid") if isinstance(check, dict) else None
            row[name + "_valid"] = value if isinstance(value, bool) else None
        spf = item.get("spf") or {}
        count = spf.get("dns_lookups")
        row["spf_dns_lookups"] = count if type(count) is int and 0 <= count <= 10000 else None
        dnssec = item.get("dnssec")
        row["dnssec"] = dnssec if isinstance(dnssec, bool) else None
        tags = (item.get("dmarc") or {}).get("tags") or {}
        for tag in ("p", "sp"):
            value = tags.get(tag)
            if isinstance(value, dict):
                value = value.get("value")
            row["dmarc_" + tag] = value if value in ("none", "quarantine", "reject") else None
        result.append(row)
    if seen != domains:
        raise ValueError("incomplete domain coverage")
    return result


def project_nuclei(raw: Path, mapping: dict[str, str], ids: set[str]) -> list[dict]:
    results = []
    for line in read_report(raw).splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        host, template = item.get("host"), item.get("template-id")
        severity = item.get("info", {}).get("severity")
        domain = mapping.get(host) if isinstance(host, str) else None
        if not domain or template not in ids or severity not in LEVELS:
            raise ValueError("unexpected Nuclei result")
        results.append({"domain": domain, "template_id": template, "severity": severity})
    return results


def audit(rows, checker: Path, nuclei: Path, templates: Path) -> dict:
    domains = {row["name"] for row in rows}
    selectors = {f"{sel}._domainkey.{row['name']}": row["name"]
                 for row in rows for sel in row.get("dkim_selectors", [])}
    missing = sorted(row["name"] for row in rows
                     if not row.get("dkim_selectors") and row["mail_use"] != "no-mail")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": sorted(domains), "dkim_unverified_domains": missing,
              "checkdmarc_version": "6.0.3", "nuclei_version": "3.11.1",
              "template_revision": "745c8d83f2daa49b5525793229a358044a8bb3e7",
              "checkdmarc": {"status": "INCOMPLETE", "results": []},
              "nuclei_dns": {"status": "INCOMPLETE", "findings": []},
              "nuclei_dkim": {"status": "INCOMPLETE" if selectors else "NOT_RUN_NO_SELECTORS",
                              "findings": []}}
    common = [str(nuclei), "-pt", "dns", "-ni", "-rl", "2", "-c", "1",
              "-timeout", "5", "-retries", "0", "-duc", "-or", "-jsonl"]
    with tempfile.TemporaryDirectory(prefix="ctem-mail-") as tmp:
        folder = Path(tmp)
        raw = folder / "check.json"
        if execute([str(checker), *sorted(domains), "--skip-tls", "-f", "json", "-o", str(raw)], 150):
            try:
                projected = project_checkdmarc(raw, domains)
            except (OSError, TypeError, ValueError, AttributeError):
                pass
            else:
                report["checkdmarc"] = {"status": "OBSERVED_NOT_CERTIFIED", "results": projected}
        for key, mapping, ids, paths in (
            ("nuclei_dns", {d: d for d in domains}, set(TEMPLATES),
             [templates / f"{name}.yaml" for name in TEMPLATES]),
            ("nuclei_dkim", selectors, {DKIM},
             [ROOT / "config/security/ctem/dkim-published.yaml"]),
        ):
            if not mapping or not all(path.is_file() for path in paths):
                continue
            targets = folder / f"{key}.txt"
            targets.write_text("\n".join(sorted(mapping)) + "\n", encoding="utf-8")
            raw = folder / f"{key}.jsonl"
            args = [arg for path in paths for arg in ("-t", str(path))]
            if execute([*common, "-l", str(targets), *args, "-o", str(raw)], 150):
                try:
                    if not raw.exists():
                        raw.touch()
                    projected = project_nuclei(raw, mapping, ids)
                except (OSError, TypeError, ValueError, AttributeError):
                    continue
                report[key] = {"status": "OBSERVED_NOT_CERTIFIED", "findings": projected}
    incomplete = bool(missing) or any(report[key]["status"] != "OBSERVED_NOT_CERTIFIED"
                                    for key in ("checkdmarc", "nuclei_dns"))
    incomplete = incomplete or bool(selectors and report["nuclei_dkim"]["status"] != "OBSERVED_NOT_CERTIFIED")
    report["result"] = "INCOMPLETE" if incomplete else "OBSERVED_NOT_CERTIFIED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/security/public-mail-domains.json")
    parser.add_argument("--checkdmarc", type=Path, required=True)
    parser.add_argument("--nuclei", type=Path, required=True)
    parser.add_argument("--templates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(load_scope(args.config), args.checkdmarc.resolve(),
                   args.nuclei.resolve(), args.templates.resolve())
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"mail_deep_result={report['result']}; no raw artifacts published")
    return 3 if report["result"] == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
