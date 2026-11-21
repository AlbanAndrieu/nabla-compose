"""Compare local TrueNAS and outside-in Amass reports without publishing hostnames.

The outside-in source is a GitHub Actions counts-only artifact. Its results
are NOT considered reachability evidence or a complete census of Internet
exposure. Never infer host-level differences from aggregate counts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "config/security/public-mail-domains.json"
REVISION = re.compile(r"sha256:[a-f0-9]{64}\Z")
MAX_INPUT = 2_000_000
MAX_AGE = timedelta(days=14)
MAX_SKEW = timedelta(days=7)


def private_report(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CTEM input missing or symlink")
    info = path.stat()
    if info.st_size == 0 or info.st_size > MAX_INPUT or info.st_mode & 0o077:
        raise ValueError("CTEM report not bounded or private")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "candidates" in doc or "catalogPolicyConflicts" in doc:
        raise ValueError("CTEM private candidate data forbidden in comparison")
    return doc


def validate(doc: dict, vantage: str, *, now: datetime) -> dict:
    if (doc.get("schema_version") != 1 or doc.get("scanner") != "amass"
            or doc.get("scanner_version") != "5.1.3"
            or doc.get("scan_mode") != "active" or doc.get("vantage") != vantage
            or doc.get("status") != "OBSERVED_NOT_CERTIFIED"):
        raise ValueError("CTEM vantage mode or status incomplete")
    rec = doc.get("catalogReconciliation")
    if (not isinstance(rec, dict)
            or rec.get("status") != "OBSERVED_NOT_CERTIFIED"
            or not REVISION.fullmatch(str(rec.get("catalogRevision", "")))):
        raise ValueError("CTEM catalog not reconciled")
    scope_doc = json.loads(SCOPE.read_text(encoding="utf-8"))["domains"]
    domain_set = {x["name"] for x in scope_doc}
    if len(domain_set) != len(scope_doc) or doc.get("scope") != sorted(domain_set):
        raise ValueError("CTEM scope mismatch")
    counts = doc.get("counts")
    if (not isinstance(counts, dict) or set(counts) != domain_set
            or any(type(v) is not int or not 0 <= v <= 1_000_000
                   for v in counts.values())):
        raise ValueError("CTEM counts invalid")
    checked = datetime.fromisoformat(doc["checked_at"].replace("Z", "+00:00"))
    if checked.tzinfo is None or not timedelta(0) <= now - checked <= MAX_AGE:
        raise ValueError("CTEM observation stale or future")
    return {"at": checked, "counts": counts, "revision": rec["catalogRevision"]}


def compare(internal: dict, external: dict, *, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    local = validate(internal, "truenas-internal", now=current)
    outside = validate(external, "external-github-hosted", now=current)
    if abs(local["at"] - outside["at"]) > MAX_SKEW:
        raise ValueError("CTEM observations too far apart to compare")
    if local["revision"] != outside["revision"]:
        raise ValueError("CTEM catalog revisions differ")
    diffs = []
    for domain in sorted(local["counts"]):
        a, b = local["counts"][domain], outside["counts"][domain]
        diffs.append({
            "domain": domain,
            "truenas_count": a,
            "external_count": b,
            "count_delta_external_minus_truenas": b - a,
            "comparison": "SAME_COUNT" if a == b else "COUNT_DIFFERENCE_REVIEW",
        })
    return {
        "schema_version": 1,
        "check": "ctem-amass-vantage-count-comparison",
        "status": "COUNT_DIFFERENCE_REVIEW" if any(x["comparison"] != "SAME_COUNT" for x in diffs)
                  else "SAME_COUNTS_NOT_SAME_ASSETS",
        "checked_at": current.isoformat(),
        "internal_observed_at": local["at"].isoformat(),
        "external_observed_at": outside["at"].isoformat(),
        "catalogRevision": local["revision"],
        "rows": diffs,
        "scopeCompleteness": "NOT_VERIFIED",
        "semantics": "AGGREGATE_COUNTS_ONLY_NOT_HOST_DIFFERENCE_OR_REACHABILITY_PROOF",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--internal", type=Path, required=True)
    p.add_argument("--external", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = compare(private_report(args.internal), private_report(args.external))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        print("ctem_vantage=INCOMPLETE; reason=INVALID_OR_UNMATCHED_EVIDENCE")
        return 3
    if args.output.is_symlink() or args.output.parent.is_symlink():
        print("ctem_vantage=INCOMPLETE; reason=UNSAFE_OUTPUT")
        return 3
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("ctem_vantage=" + result["status"] +
          "; scope_domains=" + str(len(result["rows"])) +
          "; no hostnames or candidate lists logged")
    # Difference is review signal, not a pipeline failure or a DOWN verdict.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
