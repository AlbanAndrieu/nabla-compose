#!/usr/bin/env python3
"""Backup-first repair of *empty only* DSOMM runtime assessment YAML.

Never overwrites non-empty assessments. Explicit --apply required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = Path("/mnt/cpool/dsomm/state")
FILES = (
    ("team-progress.yaml", "team-progress.seed.yaml", "progress"),
    ("team-evidence.yaml", "team-evidence.seed.yaml", "evidence"),
)


def check_empty(path: Path, field: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: missing/nonregular/symlink file")
    if path.stat().st_nlink != 1:
        raise ValueError(f"{path}: hardlink not accepted")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {field} or data[field] not in (None, {}):
        raise ValueError(f"{path}: not a recognized empty {field} document; refuse replacement")


def run(state: Path, apply: bool) -> int:
    if state.is_symlink() or not state.is_dir():
        raise ValueError(f"{state}: unsafe/missing state directory")
    pairs = []
    for name, seedname, field in FILES:
        current = state / name
        seed = ROOT / "apps" / "dsomm" / "config" / seedname
        check_empty(current, field)
        seeddata = yaml.safe_load(seed.read_text(encoding="utf-8"))
        if not isinstance(seeddata, dict) or not isinstance(seeddata.get(field), dict) or not seeddata[field]:
            raise ValueError(f"{seed}: seed not populated")
        pairs.append((current, seed))
    if not apply:
        print("OK: both runtime documents are recognized empty; --apply creates timestamped backup before seed initialization")
        return 0

    backup = state / ("backup-empty-assessment-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    backup.mkdir(mode=0o700)
    for current, _ in pairs:
        shutil.copy2(current, backup / current.name)
        os.chmod(backup / current.name, 0o600)
    # Preflight both before writing either; never deliberately change existing populated documents.
    for current, seed in pairs:
        check_empty(current, "progress" if current.name == "team-progress.yaml" else "evidence")
        tmp = current.with_name(current.name + f".seed-{os.getpid()}.tmp")
        try:
            with tmp.open("xb") as out:
                os.fchmod(out.fileno(), 0o600)
                out.write(seed.read_bytes())
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, current)
        finally:
            tmp.unlink(missing_ok=True)
    print(f"OK: initialized reviewed 22-activity DSOMM seed; original empty documents backed up at {backup}")
    print("INFO: container may need controlled redeploy or browser reload to reflect the YAML; no runtime restart performed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("select exactly one of --check / --apply")
    try:
        return run(args.state_root, args.apply)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"DSOMM_EMPTY_STATE_REPAIR_REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
