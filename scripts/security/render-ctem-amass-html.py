#!/usr/bin/env python3
"""Render a local-only, self-contained CTEM Amass report (no remote assets).

The generated file is root-owned 0600 and MUST NOT be web-served.
Only private, exact, same-run candidate exports can be rendered.
No Javascript, analytics or CDN dependencies; content is HTML-escaped.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path
import re
import stat

MAX_BYTES = 8_000_000
MAX_ROWS = 20_000
REVISION = re.compile(r"sha256:[a-f0-9]{64}\Z")
DNS = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CTEM report missing or symbolic link")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES or st.st_mode & 0o077:
        raise ValueError("CTEM report must be bounded and owner-private")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("CTEM report must be JSON object")
    return value


def validate_pair(summary: dict, private: dict) -> list[dict]:
    for key in ("schema_version", "scanner", "scanner_version",
                "scan_mode", "checked_at", "status", "vantage", "counts"):
        if summary.get(key) != private.get(key):
            raise ValueError("CTEM source and private candidates not same scan")
    if summary.get("schema_version") != 1 or summary.get("scanner") != "amass":
        raise ValueError("unrecognized CTEM scan schema")
    if summary.get("status") != "OBSERVED_NOT_CERTIFIED":
        raise ValueError("do not present an incomplete Amass scan as a complete visualization")
    rec = summary.get("catalogReconciliation")
    if not isinstance(rec, dict) or not REVISION.fullmatch(str(rec.get("catalogRevision", ""))):
        raise ValueError("missing V2 catalog revision")
    if rec.get("status") != "OBSERVED_NOT_CERTIFIED":
        raise ValueError("catalog reconciliation incomplete")
    if summary.get("catalogReconciliation") != private.get("catalogReconciliation"):
        raise ValueError("catalog discrepancy between private and public artifacts")
    rows = private.get("candidates")
    counts = summary.get("counts")
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            not isinstance(counts, dict)):
        raise ValueError("unbounded CTEM candidates or counts")
    seen = set()
    calculated = Counter()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("malformed CTEM candidate")
        host, domain = item.get("hostname"), item.get("domain")
        if (not isinstance(host, str) or not isinstance(domain, str)
                or not DNS.fullmatch(host) or not DNS.fullmatch(domain)
                or not (host == domain or host.endswith("." + domain))
                or host in seen):
            raise ValueError("invalid, out-of-scope or repeated hostname")
        matches = item.get("catalogMatches")
        if not isinstance(matches, list) or len(matches) > 20:
            raise ValueError("unbounded catalog mapping")
        for match in matches:
            if not isinstance(match, dict) or not isinstance(match.get("entityRef"), str):
                raise ValueError("invalid catalog mapping")
        state = item.get("catalogMatch")
        if state not in {
            "MATCHED_PUBLIC_INTENT", "LAN_ONLY_POLICY_REVIEW",
            "NON_PUBLIC_INTENT_REVIEW", "AMBIGUOUS_ENTITY_REVIEW",
            "UNMAPPED_REVIEW",
        }:
            raise ValueError("invalid CTEM reconciliation classification")
        seen.add(host)
        calculated[domain] += 1
    if {name: calculated[name] for name in counts} != counts or len(seen) != sum(counts.values()):
        raise ValueError("CTEM candidate count mismatch")
    return sorted(rows, key=lambda r: (r["domain"], r["hostname"]))


def page(summary: dict, private: dict) -> str:
    rows = validate_pair(summary, private)
    counts = summary["counts"]
    states = Counter(row["catalogMatch"] for row in rows)
    checked_at = escape(str(summary["checked_at"]))
    revision = escape(summary["catalogReconciliation"]["catalogRevision"][:20])
    table = []
    for item in rows:
        mapping = ", ".join(
            escape(m["entityRef"]) for m in item["catalogMatches"]
        ) or "—"
        table.append(
            "<tr><td><code>" + escape(item["hostname"]) + "</code></td>"
            "<td>" + escape(item["domain"]) + "</td>"
            "<td>" + escape(item["catalogMatch"]) + "</td>"
            "<td>" + mapping + "</td></tr>"
        )
    scopes = "".join(
        "<li><b>" + escape(domain) + "</b> — " + str(n) + "</li>"
        for domain, n in sorted(counts.items())
    )
    groups = "".join(
        "<li><b>" + escape(state) + "</b> — " + str(count) + "</li>"
        for state, count in sorted(states.items())
    )
    header = (
        "<meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>CTEM — Amass private inventory</title>"
    )
    style = (
        "<style>body{font:15px system-ui,sans-serif;max-width:1180px;margin:auto;"
        "padding:2rem;color:#182232;background:#f6f8fb}"
        "h1,h2{letter-spacing:-.025em}section{background:white;border:1px solid #e0e6ed;"
        "border-radius:10px;padding:1.2rem;margin-bottom:1.1rem}"
        "code{font-size:13px}table{border-collapse:collapse;width:100%;font-size:13px}"
        "td,th{text-align:left;border-bottom:1px solid #e5e9ef;padding:.6rem;overflow-wrap:anywhere}"
        "th{position:sticky;top:0;background:#fff}small{color:#5b6574}"
        "ul{columns:2;line-height:2} .scroll{overflow:auto;max-height:62vh}"
        "</style>"
    )
    return (
        "<!doctype html><html lang='fr'><head>" + header + style + "</head><body>"
        "<h1>CTEM · Inventaire Amass privé</h1><p><small>Fichier local confidentiel. "
        "Observations de découverte, pas une preuve de vulnérabilité ni d'exposition WAN.</small></p>"
        "<section><h2>Contexte</h2><p><b>Observation :</b> " + escape(str(summary["vantage"])) +
        " · <b>Mode :</b> " + escape(str(summary["scan_mode"])) +
        " · <b>Horodatage :</b> " + checked_at +
        " · <b>Révision V2 :</b> " + revision + "…</p>"
        "<p><b>Nombre de noms :</b> " + str(len(rows)) + "</p></section>"
        "<section><h2>Couverture par domaine</h2><ul>" + scopes + "</ul></section>"
        "<section><h2>Rapprochement Backstage V2</h2><ul>" + groups + "</ul></section>"
        "<section><h2>Candidats nominatifs</h2><div class='scroll'><table>"
        "<thead><tr><th>FQDN</th><th>Domaine</th><th>Statut déclaratif</th><th>Entité V2</th>"
        "</tr></thead><tbody>" + "".join(table) + "</tbody></table></div></section>"
        "</body></html>"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output == args.summary or args.output == args.private:
        p.error("output must differ from inputs")
    summary = private_json(args.summary)
    private = private_json(args.private)
    rendered = page(summary, private)
    if args.output.is_symlink() or not args.output.parent.is_dir():
        p.error("private output directory missing or symlink")
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(rendered)
    print(f"CTEM private dashboard generated; candidate_count={len(private['candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
