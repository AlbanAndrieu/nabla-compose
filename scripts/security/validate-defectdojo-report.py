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
            if not isinstance(entry, dict):
                raise ValueError("invalid Nuclei finding")
            url = entry.get("matched-at") or entry.get("host", "")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in spec["hosts"]:
                raise ValueError("Nuclei target is not in the permitted HTTPS domain set")
            if service == "nabla-site-alban":
                if parsed.username or parsed.password or parsed.port not in (None, 443):
                    raise ValueError("Nuclei userinfo and custom ports forbidden")
                if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                    raise ValueError("Nuclei URL must be minimized to origin")
                info = entry.get("info")
                if not isinstance(info, dict) or info.get("severity") not in {"high", "critical"}:
                    raise ValueError("unexpected Nuclei severity")
                if not isinstance(entry.get("template-id"), str) or not entry["template-id"]:
                    raise ValueError("Nuclei template identity missing")
                if set(entry) - {"template-id", "type", "info", "matched-at"}:
                    raise ValueError("raw Nuclei HTTP evidence forbidden")
                if set(info) - {"name", "severity"}:
                    raise ValueError("unapproved Nuclei description or evidence")
        return
    if scanner == "ZAP Scan":
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
        if set(report) - {"SchemaVersion", "ArtifactName", "ArtifactType", "Results"}:
            raise ValueError("raw Trivy report metadata forbidden")
        approved_fields = {"VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity"}
        rows = {"nabla-site-alban": {"package-lock.json"}, "fastapi-sample": {"uv.lock"}}
        allowed_targets = rows.get(service)
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("invalid Trivy result")
            if "Secrets" in row:
                raise ValueError("Trivy secret evidence forbidden from import")
            if set(row) - {"Target", "Class", "Type", "Vulnerabilities"}:
                raise ValueError("raw Trivy evidence forbidden")
            target = row.get("Target")
            if not isinstance(target, str):
                raise ValueError("Trivy target missing")
            if allowed_targets is not None and target not in allowed_targets:
                raise ValueError("unapproved project lockfile target")
            if service == "nabla-compose":
                import re
                if not re.fullmatch(
                    r"(?:uv[.]lock|poetry[.]lock|Pipfile[.]lock|package-lock[.]json|"
                    r"pnpm-lock[.]yaml|requirements[A-Za-z0-9._-]*[.]txt)", target
                ):
                    raise ValueError("compose report must target an approved lockfile")
            findings = row.get("Vulnerabilities")
            if not isinstance(findings, list) or not findings:
                raise ValueError("Trivy report row has no actionable findings")
            for finding in findings:
                if (
                    not isinstance(finding, dict)
                    or finding.get("Severity") not in {"HIGH", "CRITICAL"}
                    or not all(
                        isinstance(finding.get(k), str) and finding[k]
                        for k in ("VulnerabilityID", "PkgName")
                    )
                    or set(finding) - approved_fields
                ):
                    raise ValueError("unapproved Trivy evidence or severity")
        if service in {"nabla-site-alban", "fastapi-sample"} and not results:
            raise ValueError("empty lockfile report")
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
