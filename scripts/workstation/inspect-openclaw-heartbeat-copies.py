#!/usr/bin/env python3
"""Metadata-only legacy heartbeat backup inventory; never read archive or MD files.

This diagnostic does NOT extract, decrypt, upload, restore, copy or chmod.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

HOME = Path.home()


def inspect(path: Path, role: str) -> dict:
    result = {"role": role, "state": "unavailable", "content_read": False}
    try:
        meta = path.lstat()
    except FileNotFoundError:
        result["state"] = "missing"
        return result
    except OSError:
        return result
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        result["state"] = "unsafe_type_or_link"
        return result
    if meta.st_uid != os.geteuid():
        result["state"] = "unexpected_owner"
        return result
    mode = stat.S_IMODE(meta.st_mode)
    result["size_bytes"] = meta.st_size
    result["permission_class"] = (
        "unsafe_writable_by_others" if mode & 0o022 else
        "readable_by_others" if mode & 0o077 else "private"
    )
    result["state"] = "present"
    return result


def inventory(legacy: Path, before_fix: Path, archive: Path) -> dict:
    sources = [
        inspect(before_fix, "workspace_before_fix"),
        inspect(legacy, "nabla_legacy_heartbeat"),
        inspect(archive, "openclaw_august_archive"),
    ]
    return {
        "sources": sources,
        "archive_extracted": False,
        "content_read": False,
        "state_modified": False,
        "archive_scan_performed": False,
        "runtime_heartbeat_restored": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--legacy", type=Path,
                        default=HOME / "w/nabla/env/home/dotfiles/.openclaw/workspace/HEARTBEAT.md")
    parser.add_argument("--before-fix", type=Path,
                        default=HOME / ".openclaw/workspace/HEARTBEAT.md.before-fix")
    parser.add_argument("--archive", type=Path,
                        default=HOME / "openclaw-backups/openclaw-2026-08-04_0220.tar.gz")
    args = parser.parse_args(argv)
    report = inventory(args.legacy, args.before_fix, args.archive)
    print(json.dumps(report, sort_keys=True))
    found = sum(x["state"] == "present" for x in report["sources"])
    insecure = any(x.get("permission_class") != "private"
                   for x in report["sources"] if x["state"] == "present")
    return 0 if found and not insecure else 2


if __name__ == "__main__":
    raise SystemExit(main())
