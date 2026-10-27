#!/usr/bin/env python3
"""Opt-in metadata-only hardening of three historical OpenClaw files.

--check is read-only; --apply changes ONLY existing owner-controlled regular
file mode bits to 0600. Never reads file data, archives, credentials, or logs.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import stat

HOME = Path.home()
SOURCES = (
    ("workspace_before_fix", HOME / ".openclaw/workspace/HEARTBEAT.md.before-fix",
     "HEARTBEAT.md.before-fix"),
    ("nabla_legacy_heartbeat", HOME / "w/nabla/env/home/dotfiles/.openclaw/workspace/HEARTBEAT.md",
     "HEARTBEAT.md"),
    ("openclaw_august_archive", HOME / "openclaw-backups/openclaw-2026-08-04_0220.tar.gz",
     "openclaw-2026-08-04_0220.tar.gz"),
)


def source_check(path: Path, expected_basename: str):
    """Return (status, fd, inode) with no content read and no path output."""
    if path.name != expected_basename:
        return "unexpected_filename", None, None
    try:
        if any(parent.is_symlink() for parent in path.parents):
            return "symlinked_parent", None, None
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return "unsafe_type_or_link", None, None
        if before.st_uid != os.geteuid():
            return "unexpected_owner", None, None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        current = os.fstat(fd)
        if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                or current.st_uid != os.geteuid()
                or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
            os.close(fd)
            return "changed_or_unsafe", None, None
        mode = stat.S_IMODE(current.st_mode)
        return ("private" if mode == 0o600 else "needs_mode_0600"), fd, (
            current.st_dev, current.st_ino)
    except FileNotFoundError:
        return "missing", None, None
    except OSError:
        return "unavailable", None, None


def reconcile(entries, *, apply: bool) -> tuple[dict, int]:
    rows = []
    with ExitStack() as stack:
        opened = []
        for role, path, basename in entries:
            status, fd, identity = source_check(path, basename)
            rows.append({"role": role, "state": status})
            if fd is not None:
                stack.callback(os.close, fd)
                opened.append((path, fd, identity))
        valid = len(opened) == len(entries) and all(
            row["state"] in ("private", "needs_mode_0600") for row in rows)
        unique = len({x[2] for x in opened}) == len(opened)
        changed = 0
        if apply and valid and unique:
            # Recheck all identities before the first operation.
            for path, fd, identity in opened:
                current = path.lstat()
                if (current.st_dev, current.st_ino) != identity:
                    valid = False
                    break
            if valid:
                for path, fd, identity in opened:
                    try:
                        # Avoid touching ctime if already private.
                        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                            os.fchmod(fd, 0o600)
                            changed += 1
                        current = path.lstat()
                        if ((current.st_dev, current.st_ino) != identity
                                or stat.S_IMODE(os.fstat(fd).st_mode) != 0o600):
                            valid = False
                            break
                    except OSError:
                        valid = False
                        break
        secure = valid and unique and (apply or all(
            row["state"] == "private" for row in rows))
        if apply and secure:
            rows = [{**row, "state": "private"} for row in rows]
        report = {
            "schema": "openclaw-heartbeat-copies-mode/v1",
            "operation": "apply_mode_private" if apply else "read_only_check",
            "sources": rows,
            "target_mode": "0600",
            "files_mode_updated": changed if apply else 0,
            "all_private": secure,
            "content_read": False,
            "archive_extracted": False,
            "session_or_gateway_mutated": False,
            "secrets_printed": False,
        }
        return report, 0 if secure else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true",
                       help="Explicitly restrict the three existing files to mode 0600")
    for flag, (_, default_path, _) in zip(("before-fix", "legacy", "archive"), SOURCES):
        parser.add_argument("--" + flag, type=Path, default=default_path)
    args = parser.parse_args(argv)
    entries = tuple((spec[0], getattr(args, attr), spec[2])
                    for attr, spec in zip(("before_fix", "legacy", "archive"), SOURCES))
    result, exit_code = reconcile(entries, apply=args.apply)
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
