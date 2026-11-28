#!/usr/bin/env python3
"""Read-only, private CTEM/DefectDojo import evidence; never queries servers.

GitHub artifact availability, a local staging file and API acknowledgement
are separate from successful DefectDojo processing. Never print raw findings.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path("/mnt/cpool/defectdojo")
MAX_CHILDREN = 256
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\Z")
SOURCES = (
    ("compose", "imports/nabla-compose", re.compile(r"compose-([1-9][0-9]*)-trivy\.json\Z")),
    ("fastapi-sample", "imports/fastapi-sample", re.compile(r"fastapi-([1-9][0-9]*)-trivy\.json\Z")),
    ("site-alban", "imports/site-alban", re.compile(r"site-alban-([1-9][0-9]*)-(trivy|nuclei|zap)\.(json|xml)\Z")),
    ("site-bababou", "imports/site-bababou", re.compile(r"site-bababou-([1-9][0-9]*)-zap\.xml\Z")),
)


def private_file(path: Path, limit: int = 100_000_000) -> bool:
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit
                and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0)
    except OSError:
        return False


def private_dir(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISDIR(info.st_mode) and info.st_mode & 0o077 == 0
    except OSError:
        return False


def read_json(path: Path) -> dict | None:
    if not private_file(path, 16_384):
        return None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            meta = os.fstat(stream.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_size > 16_384:
                return None
            value = json.loads(stream.read(16_385))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def digest(path: Path) -> str | None:
    if not private_file(path):
        return None
    h = sha256()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def age(path: Path, now: datetime) -> str:
    try:
        time = datetime.fromtimestamp(path.lstat().st_mtime, timezone.utc)
    except (OSError, OverflowError, ValueError):
        return "UNVERIFIED"
    delta = now - time
    return "FRESH" if timedelta(0) <= delta <= timedelta(days=7) else "STALE"


def staged_state(path: Path, source: str, run_id: int) -> str:
    if not private_file(path):
        return "INVALID_EVIDENCE"
    if source != "fastapi-sample":
        return "STAGED_NO_IMPORT_PROOF"
    marker = path.with_suffix(".import.json")
    if not marker.exists() and not marker.is_symlink():
        return "STAGED_NO_IMPORT_PROOF"
    obj = read_json(marker)
    if obj is None or set(obj) != {"run_id", "sha256", "engagement", "state"}:
        return "INVALID_EVIDENCE"
    if (type(obj["run_id"]) is not int or obj["run_id"] != run_id
            or not isinstance(obj["sha256"], str)
            or obj["sha256"] != digest(path)
            or not isinstance(obj["engagement"], str)
            or re.fullmatch(r"[1-9][0-9]*", obj["engagement"]) is None):
        return "INTEGRITY_MISMATCH"
    return {"pending_review": "PENDING_REVIEW",
            "acknowledged": "API_ACKNOWLEDGED_UNVERIFIED"}.get(
                obj["state"], "INVALID_EVIDENCE")


def private_zap(path: Path) -> tuple[str, str]:
    manifest = read_json(path / "manifest.json")
    if manifest is None or manifest.get("run_id") != path.name:
        return "INVALID_EVIDENCE", "NOT_VERIFIED"
    if manifest.get("scan_state") != "COMPLETE":
        return "INCOMPLETE_SCAN", "NOT_VERIFIED"
    outputs = manifest.get("outputs")
    expected = outputs.get("report-full.xml") if isinstance(outputs, dict) else None
    if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
        return "INVALID_EVIDENCE", "NOT_VERIFIED"
    if digest(path / "report-full.xml") != expected["sha256"]:
        return "INTEGRITY_MISMATCH", "NOT_VERIFIED"
    state = manifest.get("import_state")
    if state == "NOT_STARTED":
        return "COMPLETE", "NOT_IMPORTED"
    if state == "FAILED":
        return "COMPLETE", "IMPORT_FAILED"
    if state in {"PENDING", "API_ACCEPTED_UNVERIFIED"}:
        return "COMPLETE", "API_ACKNOWLEDGED_UNVERIFIED"
    if state != "CONFIRMED":
        return "COMPLETE", "UNVERIFIED"
    name = manifest.get("last_import_receipt")
    if (not isinstance(name, str) or re.fullmatch(
            r"defectdojo-response(?:-retry-[0-9a-f]{8})?\.json", name) is None):
        return "COMPLETE", "UNVERIFIED"
    receipt = read_json(path / name)
    if receipt is None:
        return "COMPLETE", "UNVERIFIED"
    test = receipt.get("test_id", receipt.get("test"))
    if type(test) is not int or test <= 0:
        return "COMPLETE", "UNVERIFIED"
    if (receipt.get("status") == "Processed"
            and receipt.get("processing") is not True):
        return "COMPLETE", "ARCHIVED_PROCESSING_CONFIRMED"
    if (receipt.get("background_import") is False
            and isinstance(receipt.get("statistics"), dict)):
        return "COMPLETE", "ARCHIVED_PROCESSING_CONFIRMED"
    return "COMPLETE", "API_ACKNOWLEDGED_UNVERIFIED"


def inventory(root: Path, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    rows = []
    for source, folder, pattern in SOURCES:
        directory = root / folder
        if not private_dir(directory):
            rows.append({"source": source, "state": "NOT_OBSERVED",
                         "import": "NOT_VERIFIED", "freshness": "UNVERIFIED"})
            continue
        try:
            children = list(directory.iterdir())
        except OSError:
            children = []
        if len(children) > MAX_CHILDREN:
            rows.append({"source": source, "state": "INCOMPLETE_INVENTORY",
                         "import": "NOT_VERIFIED", "freshness": "UNVERIFIED"})
            continue
        count = 0
        for path in sorted(children, key=lambda x: x.name):
            match = pattern.fullmatch(path.name)
            if match is None:
                continue
            count += 1
            id_number = int(match.group(1))
            status = staged_state(path, source, id_number)
            rows.append({"source": source, "run_id": id_number,
                         "scanner": (match.group(2) if source == "site-alban"
                                     else "trivy" if source in {"compose", "fastapi-sample"}
                                     else "zap"),
                         "state": ("INVALID_EVIDENCE" if status in
                                   {"INVALID_EVIDENCE", "INTEGRITY_MISMATCH"} else "STAGED"),
                         "import": status, "freshness": age(path, now)})
        if not count:
            rows.append({"source": source, "state": "NOT_OBSERVED",
                         "import": "NOT_VERIFIED", "freshness": "UNVERIFIED"})
    directory = root / "private-zap/site-alban/runs"
    if private_dir(directory):
        try:
            children = list(directory.iterdir())
        except OSError:
            children = []
        if len(children) > MAX_CHILDREN:
            rows.append({"source": "site-alban-private", "scanner": "zap",
                         "state": "INCOMPLETE_INVENTORY", "import": "NOT_VERIFIED"})
        else:
            for path in sorted(children, key=lambda x: x.name):
                if RUN_ID.fullmatch(path.name) is None:
                    continue
                state, imported = (private_zap(path) if private_dir(path) else
                                   ("INVALID_EVIDENCE", "NOT_VERIFIED"))
                rows.append({"source": "site-alban-private", "scanner": "zap",
                             "run_id": path.name, "state": state,
                             "import": imported, "freshness": age(path / "manifest.json", now)})
    else:
        rows.append({"source": "site-alban-private", "scanner": "zap",
                     "state": "NOT_OBSERVED", "import": "NOT_VERIFIED",
                     "freshness": "UNVERIFIED"})
    return {
        "schema_version": 1, "generated_at": now.isoformat(),
        "scope": "private-archive-read-only; no network queries",
        "counts": dict(sorted(Counter(row["import"] for row in rows).items())),
        "records": rows, "finding_count": None,
        "defectdojo_live_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="offline contract only")
    mode.add_argument("--report", action="store_true", help="inspect private archive")
    args = parser.parse_args()
    if args.check:
        if len({source for source, _, _ in SOURCES}) != len(SOURCES):
            raise SystemExit("duplicate source")
        print("CTEM_PRIVATE_EVIDENCE_CONTRACT_OK network=false")
        return 0
    if os.geteuid() != 0:
        parser.error("private report requires local root read permissions")
    print(json.dumps(inventory(ROOT, datetime.now(timezone.utc)), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
