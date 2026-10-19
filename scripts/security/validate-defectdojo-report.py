#!/usr/bin/env python3
"""Fail-closed allowlist and schema validation for private DefectDojo imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/security/defectdojo-allowed-imports.json"


def validate(service: str, scanner: str, data: bytes) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if not policy.get("defaultDeny"):
        raise ValueError("policy must default deny")
    spec = policy["producers"].get(service)
    if not spec or scanner not in spec["allow"] or scanner in policy["deny"]:
        raise ValueError("project/scan parser not on the explicit allowlist")
    if len(data) == 0 or len(data) > 10_000_000:
        raise ValueError("invalid report size")
    if scanner == "Nuclei Scan":
        results = []
        for line in data.splitlines():
            if line.strip():
                results.append(json.loads(line))
        if not results:
            raise ValueError("empty Nuclei report")
        for entry in results:
            url = entry.get("matched-at") or entry.get("host", "")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in spec["hosts"]:
                raise ValueError("Nuclei target is not in the permitted HTTPS domain set")
        return
    if scanner == "Zed Attack Proxy":
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("XML entities and document types forbidden")
        try:
            root = ElementTree.fromstring(data)
        except ElementTree.ParseError as exc:
            raise ValueError("invalid ZAP XML report") from exc
        if root.tag != "OWASPZAPReport":
            raise ValueError("expected OWASP ZAP XML report")
        sites = root.findall("site")
        if not sites:
            raise ValueError("empty ZAP XML target set")
        total = 0
        for site in sites:
            uri = urlsplit(site.get("name", ""))
            if uri.scheme != "https" or uri.hostname not in spec["hosts"] or uri.query or uri.fragment:
                raise ValueError("ZAP target outside permitted HTTPS hosts")
            for alert in site.findall("alerts/alertitem"):
                if alert.findtext("riskcode") != "3" or not (alert.findtext("pluginid") or "").isdecimal():
                    raise ValueError("unexpected ZAP alert content")
                if alert.find("requestheader") is not None or alert.find("responseheader") is not None:
                    raise ValueError("raw ZAP requests forbidden")
                for instance in alert.findall("instances/instance"):
                    url = urlsplit(instance.findtext("uri", ""))
                    if (
                        url.scheme != "https"
                        or url.hostname not in spec["hosts"]
                        or url.query or url.fragment
                    ):
                        raise ValueError("unsafe ZAP instance URL")
                    if any(instance.find(p) is not None for p in ("requestheader", "requestbody", "responseheader", "responsebody", "evidence", "param", "attack")):
                        raise ValueError("raw ZAP HTTP evidence forbidden")
                total += 1
        if total == 0:
            raise ValueError("no actionable ZAP alerts")
        return
    report = json.loads(data)
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    if scanner == "Trivy Scan":
        results = report.get("Results")
        if not isinstance(results, list):
            raise ValueError("not a Trivy report")
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("invalid Trivy result")
            if row.get("Secrets"):
                raise ValueError("Trivy secret evidence forbidden from import")
    elif scanner == "CodeQL Scan":
        if report.get("version") != "2.1.0" or not isinstance(report.get("runs"), list):
            raise ValueError("invalid CodeQL SARIF")
        if not report["runs"] or not any(
            "codeql" in str(run.get("tool", {}).get("driver", {}).get("name", "")).lower()
            for run in report["runs"] if isinstance(run, dict)
        ):
            raise ValueError("CodeQL SARIF tool identity missing")
    elif scanner == "Semgrep JSON Report":
        if not isinstance(report.get("results"), list):
            raise ValueError("not a Semgrep report")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--scan-type", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.report.is_absolute() or args.report.is_symlink() or not args.report.is_file():
        parser.error("absolute regular non-symlink report required")
    try:
        validate(args.service, args.scan_type, args.report.read_bytes())
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.error(f"report rejected: {exc}")
    print(f"ACCEPTABLE: {args.service} / {args.scan_type} (offline schema and scope only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
