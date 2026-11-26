#!/usr/bin/env python3
"""Read-only GitHub security evidence; a green CI run is not a scan attestation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Exact repository/workflow allowlist. Never accept user-supplied URLs.
CONTROLS = (
    ("compose-codeql", "nabla-compose", "codeql.yml", "SAST", None),
    ("compose-sca", "nabla-compose", "security-source-sca.yml", "SCA", None),
    ("compose-external", "nabla-compose", "external-attack-surface.yml", "DAST", "external-attack-surface-"),
    ("compose-trivy", "nabla-compose", "defectdojo-compose-handoff.yml", "SCA", "defectdojo-compose-trivy-"),
    ("alban-trivy", "nabla-site-alban", "security-supply-chain.yml", "SCA", "trivy-master-"),
    ("alban-nuclei", "nabla-site-alban", "nuclei-public.yml", "DAST", "nuclei-public-"),
    ("alban-zap", "nabla-site-alban", "master-dast.yml", "DAST", "zap-production-report"),
    ("bababou-deep", "nabla-site-bababou", "security-deep.yml", "SAST/SCA/DAST", "semgrep-master-"),
    ("bababou-zap", "nabla-site-bababou", "production-dast.yml", "DAST", "zap-production-report"),
    ("fastapi-codeql", "fastapi-sample", "codeql.yml", "SAST", None),
    ("fastapi-trivy", "fastapi-sample", "docker-build.yml", "SCA", "defectdojo-fastapi-trivy-"),
)
PRIVATE = ("defectdojo-import", "dependency-track", "plumber", "prowler",
           "trivy-k8s", "freshrss-security", "dependabot-updates")
TRUSTED_EVENTS = {"schedule", "push", "workflow_dispatch", "repository_dispatch"}


def github_get(url):
    if not url.startswith("https://api.github.com/repos/AlbanAndrieu/"):
        raise ValueError("URL not allowlisted")
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=12) as result:
        body = result.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("oversized response")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("malformed response")
    return payload


def classify(run):
    if run.get("status") != "completed":
        return "INCOMPLETE"
    return {"success": "CI_SUCCESS", "failure": "CI_FAILED",
            "cancelled": "INCOMPLETE", "timed_out": "INCOMPLETE",
            "skipped": "NOT_RUN"}.get(run.get("conclusion"), "UNVERIFIED")


def build_report(fetch, now):
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    rows = []
    for identity, short, workflow, category, artifact_prefix in CONTROLS:
        repo = "AlbanAndrieu/" + short
        row = {"id": identity, "category": category, "repository": repo,
               "workflow": workflow, "execution": "UNVERIFIED",
               "freshness": "UNVERIFIED",
               "artifact": "UNVERIFIED" if artifact_prefix else "NOT_APPLICABLE",
               "defectdojo_import": "NOT_VERIFIED", "scan_validated": False,
               "findings": None, "run_id": None, "run_url": None}
        url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
               f"{workflow}/runs?branch=master&per_page=10")
        try:
            runs = fetch(url)["workflow_runs"]
            if not isinstance(runs, list):
                raise ValueError("invalid runs")
            # The newest eligible run wins, even when failed. No green fallback.
            latest = next((r for r in runs if isinstance(r, dict)
                           and r.get("head_branch") == "master"
                           and r.get("event") in TRUSTED_EVENTS), None)
            if latest is None:
                row["execution"] = "NOT_RUN"
            else:
                row["execution"] = classify(latest)
                run_id = latest.get("id")
                if type(run_id) is int and run_id > 0:
                    row["run_id"] = run_id
                    row["run_url"] = f"https://github.com/{repo}/actions/runs/{run_id}"
                updated = latest.get("updated_at")
                if isinstance(updated, str):
                    at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if at.tzinfo and at <= now:
                        age = (now - at).total_seconds() / 3600
                        row["freshness"] = "FRESH" if age <= 192 else "STALE"
                if artifact_prefix and row["execution"] == "CI_SUCCESS" and row["run_id"]:
                    artifact_url = (f"https://api.github.com/repos/{repo}/actions/runs/"
                                    f"{run_id}/artifacts?per_page=100")
                    artifacts = fetch(artifact_url)["artifacts"]
                    if not isinstance(artifacts, list):
                        raise ValueError("invalid artifacts")
                    row["artifact"] = "AVAILABLE" if any(
                        isinstance(a, dict) and isinstance(a.get("name"), str)
                        and a["name"].startswith(artifact_prefix)
                        and a.get("expired") is False for a in artifacts
                    ) else "MISSING"
        except (HTTPError, URLError, TimeoutError, OSError, ValueError,
                TypeError, KeyError, json.JSONDecodeError):
            # Upstream failures do not mark services DOWN or fabricate zeroes.
            if artifact_prefix and row["artifact"] != "AVAILABLE":
                row["artifact"] = "UNVERIFIED"
        rows.append(row)
    for identity in PRIVATE:
        rows.append({"id": identity, "category": "PRIVATE",
                     "execution": "UNVERIFIED", "freshness": "UNVERIFIED",
                     "artifact": "NOT_APPLICABLE", "defectdojo_import": "NOT_VERIFIED",
                     "scan_validated": False, "findings": None,
                     "run_id": None, "run_url": None})
    return {"schema_version": 1, "generated_at": now.isoformat(),
            "meaning": "CI_SUCCESS does not prove scan coverage or DefectDojo import",
            "totals": dict(Counter(r["execution"] for r in rows)),
            "controls": rows}


def render_html(report):
    css = ("body{font:15px system-ui;max-width:1080px;margin:2rem auto;padding:0 1rem;"
           "color:#172334}table{width:100%;border-collapse:collapse}"
           "td,th{border-bottom:1px solid #cbd5e1;padding:.6rem;text-align:left}"
           "th{background:#e2e8f0}tr:nth-child(even){background:#f8fafc}"
           "@media(max-width:700px){table{display:block;overflow-x:auto}}")
    prefix = ("<!doctype html><html lang='fr'><meta charset='utf-8'>"
              "<meta name='viewport' content='width=device-width,initial-scale=1'>"
              "<title>Nabla · preuves sécurité</title><style>" + css + "</style>"
              "<main><h1>Contrôles de sécurité · Nabla</h1><p>Généré le "
              + escape(report["generated_at"])
              + " (UTC). Les résultats GitHub ne certifient ni un scan, ni un import "
              "DefectDojo. Un nombre inconnu de findings n'est pas zéro.</p>"
              "<table><tr><th>Contrôle</th><th>CI</th><th>Fraîcheur</th>"
              "<th>Artefact</th><th>DefectDojo</th><th>Run</th></tr>")
    lines = []
    for r in report["controls"]:
        cells = [r["id"], r["execution"], r["freshness"],
                 r["artifact"], r["defectdojo_import"]]
        link = (f"<a href='{escape(r['run_url'], quote=True)}'>GitHub</a>"
                if r["run_url"] else "—")
        lines.append("<tr>" + "".join("<td>" + escape(str(v)) + "</td>"
                                       for v in cells) + "<td>" + link + "</td></tr>")
    return prefix + "".join(lines) + "</table></main></html>\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("security-evidence-output"))
    args = parser.parse_args()
    if len({c[0] for c in CONTROLS}) != len(CONTROLS):
        raise SystemExit("duplicate control IDs")
    if args.check:
        print("SECURITY_EVIDENCE_CONFIG_VALID")
        return 0
    if not args.fetch:
        parser.error("use --check or --fetch")
    report = build_report(github_get, datetime.now(timezone.utc))
    if args.output_dir.is_symlink():
        raise SystemExit("refuse symlink output directory")
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (args.output_dir / "security-controls.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "security-controls.html").write_text(
        render_html(report), encoding="utf-8")
    print("SECURITY_EVIDENCE_WRITTEN")
    for status, count in sorted(report["totals"].items()):
        print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
