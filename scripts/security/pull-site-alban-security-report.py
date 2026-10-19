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
import sys
from urllib.parse import urlsplit
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zipfile import ZipFile

REPO = "AlbanAndrieu/nabla-site-alban"
INBOX = Path("/mnt/cpool/defectdojo/imports/site-alban")
MAX_ZIP_BYTES = 10_000_000
MAX_REPORT_BYTES = 8_000_000
KINDS = {
    "trivy": ("Supply Chain Security (Trivy)", "trivy-security.json", "Trivy Scan"),
    "nuclei": ("Nuclei public DAST (Site Alban)", "nuclei-results/nuclei.jsonl", "Nuclei Scan"),
    "zap": ("Production DAST", "report_json.json", "Zed Attack Proxy"),
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise SystemExit("REJECTED: " + message)



# Read-only API client; Authorization never crosses a storage redirect.
from github_actions_artifact_api import api, metadata, GitHubArtifactError  # noqa: E402
from github_app_auth import installation_token  # noqa: E402


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


APPROVED_HOSTS = frozenset({"www.albanandrieu.com", "albanandrieu.com"})


def public_origin(value: object) -> str:
    """Retain only the canonical HTTPS origin, never credentials or URL paths."""
    if not isinstance(value, str):
        fail("missing approved public target")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in APPROVED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        fail("scan result references a non-allowlisted target")
    return f"https://{parsed.hostname}"


def filter_findings(kind: str, raw: bytes) -> bytes:
    """Produce a minimal, parser-compatible report; never stage raw HTTP evidence."""
    if len(raw) > MAX_REPORT_BYTES:
        fail("extracted report exceeds private size budget")
    if kind == "nuclei":
        kept: list[str] = []
        for line in raw.decode("utf8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict) or not isinstance(item.get("info"), dict):
                fail("invalid Nuclei finding")
            severity = str(item["info"].get("severity", "")).lower()
            if severity not in {"critical", "high"}:
                continue
            origin = public_origin(item.get("matched-at") or item.get("host"))
            template = item.get("template-id") or item.get("templateID")
            name = item["info"].get("name")
            if not isinstance(template, str) or not template or len(template) > 150:
                fail("invalid Nuclei template identity")
            if not isinstance(name, str) or not name or len(name) > 200:
                fail("invalid Nuclei finding name")
            kept.append(
                json.dumps(
                    {
                        "template-id": template,
                        "type": "http",
                        "info": {"name": name, "severity": severity},
                        "matched-at": origin,
                    },
                    separators=(",", ":"),
                )
            )
        return ("\n".join(kept) + ("\n" if kept else "")).encode()

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        fail("invalid report object")

    if kind == "trivy":
        results = payload.get("Results")
        if not isinstance(results, list):
            fail("invalid Trivy results")
        safe_results = []
        fields = ("VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity")
        for result in results:
            if not isinstance(result, dict):
                fail("invalid Trivy result")
            target = result.get("Target")
            # Only the npm lockfile is approved for the site-alban product.
            if not isinstance(target, str) or not re.fullmatch(r"(?:[^/]+/)*package-lock\.json", target):
                continue
            safe_vulnerabilities = []
            for vuln in result.get("Vulnerabilities") or []:
                if not isinstance(vuln, dict):
                    fail("invalid Trivy vulnerability")
                if str(vuln.get("Severity", "")).upper() not in {"CRITICAL", "HIGH"}:
                    continue
                candidate = {k: vuln[k] for k in fields if isinstance(vuln.get(k), str)}
                if not all(k in candidate for k in ("VulnerabilityID", "PkgName", "Severity")):
                    fail("invalid Trivy vulnerability identity")
                safe_vulnerabilities.append(candidate)
            if safe_vulnerabilities:
                safe_results.append(
                    {
                        "Target": "package-lock.json",
                        "Class": "lang-pkgs",
                        "Type": "npm",
                        "Vulnerabilities": safe_vulnerabilities,
                    }
                )
        if not safe_results:
            return b""
        return json.dumps(
            {"SchemaVersion": 2, "ArtifactName": "nabla-site-alban",
             "ArtifactType": "filesystem", "Results": safe_results},
            separators=(",", ":"),
        ).encode()

    if kind == "zap":
        sites = payload.get("site")
        if not isinstance(sites, list):
            fail("invalid ZAP report")
        report = ElementTree.Element("OWASPZAPReport", {"version": "2.17"})
        count = 0
        for site in sites:
            if not isinstance(site, dict):
                fail("invalid ZAP site")
            origin = public_origin(site.get("@name"))
            host = urlsplit(origin).hostname
            element = ElementTree.SubElement(
                report, "site",
                {"name": origin, "host": host, "port": "443", "ssl": "true"},
            )
            alerts_element = ElementTree.SubElement(element, "alerts")
            alerts = site.get("alerts") or []
            if not isinstance(alerts, list):
                fail("invalid ZAP alerts")
            for alert in alerts:
                if not isinstance(alert, dict):
                    fail("invalid ZAP alert")
                if str(alert.get("riskcode")) != "3":
                    continue
                pluginid = str(alert.get("pluginid", ""))
                title = alert.get("alert")
                if not pluginid.isdecimal() or not isinstance(title, str) or not title or len(title) > 200:
                    fail("invalid ZAP alert identity")
                node = ElementTree.SubElement(alerts_element, "alertitem")
                for key, value in (
                    ("pluginid", pluginid),
                    ("alert", title),
                    ("riskcode", "3"),
                    ("confidence", "2"),
                    ("desc", "High-risk passive ZAP alert; raw HTTP evidence withheld."),
                    ("solution", "Review the finding against the private scanner evidence."),
                ):
                    ElementTree.SubElement(node, key).text = value
                instances = ElementTree.SubElement(node, "instances")
                instance = ElementTree.SubElement(instances, "instance")
                ElementTree.SubElement(instance, "uri").text = origin
                ElementTree.SubElement(instance, "method").text = "GET"
                count += 1
        if count == 0:
            return b""
        # DefectDojo's Zed Attack Proxy importer uses XML, not ZAP JSON.
        return ElementTree.tostring(report, encoding="utf-8", xml_declaration=True)
    fail("unsupported report type")

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

    token = installation_token()
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
    except (ValueError, KeyError, UnicodeError, OSError, GitHubArtifactError):
        fail("malformed archive or report")
    if not filtered or not filtered.strip():
        print("NO_ACTIONABLE_FINDINGS: nothing imported")
        return
    if INBOX.is_symlink():
        fail("inbox must not be a symlink")
    INBOX.mkdir(parents=True, exist_ok=True, mode=0o700)
    if INBOX.stat().st_uid != 0 or INBOX.stat().st_mode & 0o077:
        fail("inbox ownership/permissions must be root-only")
    suffix = "xml" if args.kind == "zap" else "json"
    out = INBOX / f"site-alban-{args.run_id}-{args.kind}.{suffix}"
    descriptor = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(filtered)
    print(f"READY: restricted report {out}; manually approve import as {scan_type}")


if __name__ == "__main__":
    main()
