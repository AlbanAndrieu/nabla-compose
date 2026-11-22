"""Export only redacted aggregate CTEM statistics to the existing TrueNAS www NFS share.

TrueNAS: /mnt/cpool/www/reports/ctem/
Workstation NFS: /media/www/reports/ctem/
Never export FQDNs, candidates, private HTML, catalog entities or DB credentials.
Publication is explicit, off by default, and independent from the scanner.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import re
import stat

SOURCE = Path("/mnt/cpool/ctem/amass/reports/summary-latest.json")
WEB = Path("/mnt/cpool/www/reports/ctem")
ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "config/security/public-mail-domains.json"
EXPECTED_CATEGORIES = {
    "MATCHED_PUBLIC_INTENT",
    "LAN_ONLY_POLICY_REVIEW",
    "NON_PUBLIC_INTENT_REVIEW",
    "AMBIGUOUS_ENTITY_REVIEW",
    "UNMAPPED_REVIEW",
}
MAX_SOURCE_BYTES = 2_000_000


def validate(report: dict, domains: set[str]) -> dict:
    """Whitelist every published field and collapse domain-level counts to totals."""
    if (report.get("schema_version") != 1
            or report.get("scanner") != "amass"
            or report.get("scanner_version") != "5.1.3"
            or report.get("scan_mode") != "active"
            or report.get("vantage") != "truenas-internal"
            or report.get("asset_database") != "shared-postgresql/assetdb"
            or report.get("status") != "OBSERVED_NOT_CERTIFIED"):
        raise ValueError("Amass report is not complete local active evidence")
    revision = report.get("catalogReconciliation")
    counts = report.get("counts")
    if (not isinstance(revision, dict)
            or revision.get("status") != "OBSERVED_NOT_CERTIFIED"
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(revision.get("catalogRevision", "")))
            or not isinstance(counts, dict)
            or set(counts) != domains or report.get("scope") != sorted(domains)
            or any(type(value) is not int or not 0 <= value <= 1_000_000
                   for value in counts.values())):
        raise ValueError("scope, catalog revision or counts invalid")
    classification = revision.get("candidateMatchCounts")
    if (not isinstance(classification, dict)
            or set(classification) != EXPECTED_CATEGORIES
            or any(type(value) is not int or value < 0
                   for value in classification.values())
            or sum(classification.values()) != sum(counts.values())):
        raise ValueError("catalog classifications do not reconcile")
    checked = report.get("checked_at")
    if not isinstance(checked, str):
        raise ValueError("missing checked_at")
    try:
        when = datetime.fromisoformat(checked.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid checked_at") from exc
    if when.tzinfo is None:
        raise ValueError("missing observation timezone")
    return {
        "schema_version": 1,
        "report": "ctem-amass-aggregates",
        "observed_at": when.isoformat(),
        "status": "OBSERVED_NOT_CERTIFIED",
        "vantage": "truenas-internal",
        "domains_in_scope": len(domains),
        "candidate_count": sum(counts.values()),
        "catalog_categories": {k: classification[k] for k in sorted(EXPECTED_CATEGORIES)},
        "interpretation": "ASSET_CANDIDATES_NOT_CONFIRMED_PUBLIC_EXPOSURES_OR_VULNERABILITIES",
    }


def read_private(path: Path, *, require_root: bool) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source missing or symlink")
    st = path.stat()
    if (not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_SOURCE_BYTES
            or st.st_mode & 0o077 or (require_root and st.st_uid != 0)):
        raise ValueError("source is not bounded and private")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("source is not a JSON object")
    return data


def html_page(public: dict) -> str:
    """Static, no script, no remote assets and no domains."""
    categories = "".join(
        "<tr><td>" + escape(category) + "</td><td>" + str(count) + "</td></tr>"
        for category, count in public["catalog_categories"].items()
    )
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='robots' content='noindex,nofollow,noarchive'>"
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'\">"
        "<title>CTEM · synthèse expurgée</title>"
        "<style>body{font:16px system-ui,sans-serif;max-width:920px;margin:3rem auto;"
        "padding:0 1rem}td,th{padding:.65rem;border-bottom:1px solid #ddd;"
        "text-align:left}table{border-collapse:collapse;width:100%}</style>"
        "</head><body><h1>CTEM · inventaire Amass agrégé</h1>"
        "<p>Observations, non preuve de vulnérabilité ou d'exposition WAN.</p>"
        "<p>Source : " + escape(public["vantage"])
        + " · Dernier constat : " + escape(public["observed_at"]) + "</p>"
        "<p>Domaines évalués : " + str(public["domains_in_scope"])
        + " · Candidats : " + str(public["candidate_count"]) + "</p>"
        "<table><thead><tr><th>Statut déclaratif</th><th>Total</th></tr></thead>"
        "<tbody>" + categories + "</tbody></table></body></html>\n"
    )


def ensure_destination() -> None:
    """Never create the NFS export, follow redirects or remount anything."""
    root = Path("/mnt/cpool/www")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("existing NFS www source not available")
    if not os.path.ismount(root):
        raise ValueError("TrueNAS www dataset is not mounted; refuse accidental local fallback")
    parent = root / "reports"
    for directory in (parent, WEB):
        if directory.is_symlink():
            raise ValueError("report publication directory symlink")
        if not directory.exists():
            directory.mkdir(mode=0o755)
        if not directory.is_dir() or directory.stat().st_uid != 0:
            raise ValueError("report publication directory not root controlled")


def atomic_publish(directory: Path, filename: str, content: str) -> None:
    if directory.is_symlink() or not re.fullmatch(r"[a-z0-9-]+(?:[.]json|[.]html)", filename):
        raise ValueError("unsafe publication path")
    dest = directory / filename
    if dest.is_symlink() or (dest.exists() and not dest.is_file()):
        raise ValueError("existing destination is not regular")
    tmp = directory / (f".{filename}.tmp-{os.getpid()}")
    # Create the staging inode privately; expose only the explicitly
    # de-identified result after it has been written and fsynced.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
            # Only this validated public aggregate is made readable for Apache.
            os.fchmod(out.fileno(), 0o644)
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=SOURCE)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    options = p.parse_args()
    if options.apply and (
        os.geteuid() != 0 or os.environ.get("CTEM_WEB_PUBLISH_APPROVED") != "YES"
    ):
        p.error("root and CTEM_WEB_PUBLISH_APPROVED=YES required")
    domains = {
        row["name"] for row in json.loads(SCOPE.read_text(encoding="utf-8"))["domains"]
    }
    public = validate(read_private(options.source, require_root=options.apply), domains)
    if options.check:
        print(f"CHECK: sanitized CTEM counts-only publication; scope={public['domains_in_scope']}; "
              "no writes, no hostname list")
        return 0
    ensure_destination()
    atomic_publish(WEB, "amass-summary.json", json.dumps(public, sort_keys=True, indent=2) + "\n")
    atomic_publish(WEB, "index.html", html_page(public))
    print("PUBLISHED: sanitized CTEM aggregate under existing TrueNAS www NFS export; "
          "no private hostnames or candidate reports copied")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"REJECTED: {type(exc).__name__} (no sensitive report output)") from None
