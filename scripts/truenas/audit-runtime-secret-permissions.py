#!/usr/bin/env python3
"""Audit and narrowly reduce unsafe permissions in canonical TrueNAS secrets.

No reading secret contents. Preserves uid/gid and intentional group read/traverse.
Does not touch legacy paths or symlinks. Apply requires explicit acknowledgement.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys

ROOT = Path("/mnt/cpool/secrets/runtime")
ACK = "I_ACCEPT_SCOPED_SECRET_MODE_REPAIR"
SUFFIXES = (".env", ".env.secrets", ".env.compose")


def is_secret_name(name: str) -> bool:
    return name in SUFFIXES or (name.startswith(".env.") and name.endswith(".secrets"))


def plan(root: Path) -> tuple[list[tuple[Path, int, int]], list[str]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("canonical secret root absent or symlink")
    changes: list[tuple[Path, int, int]] = []
    blockers: list[str] = []
    stack = [root]
    visited = 0
    while stack:
        folder = stack.pop()
        for item in sorted(os.scandir(folder), key=lambda e: e.name):
            visited += 1
            if visited > 4096:
                raise ValueError("more than 4096 entries; refuse bulk chmod")
            path = Path(item.path)
            info = item.stat(follow_symlinks=False)
            kind = info.st_mode
            if stat.S_ISLNK(kind):
                blockers.append("SYMLINK: " + str(path.relative_to(root)))
                continue
            if not (stat.S_ISDIR(kind) or stat.S_ISREG(kind)):
                blockers.append("UNSUPPORTED_TYPE: " + str(path.relative_to(root)))
                continue
            if info.st_uid != 0:
                blockers.append("NON_ROOT_OWNER: " + str(path.relative_to(root)))
                continue
            if stat.S_ISDIR(kind):
                stack.append(path)
                target = stat.S_IMODE(kind) & ~0o027  # remove group write + all other access
                target |= 0o700  # ensure root can traverse/read
            elif is_secret_name(path.name):
                if info.st_nlink != 1:
                    blockers.append("HARDLINK: " + str(path.relative_to(root)))
                    continue
                target = stat.S_IMODE(kind) & ~0o137  # no exec, no g-write, no other
                target |= 0o600  # owner can read and write
            else:
                # Do not interpret unknown files as dotenv/credentials.
                continue
            mode = stat.S_IMODE(kind)
            if target != mode:
                changes.append((path, mode, target))
    return changes, blockers


def apply_changes(root: Path, changes: list[tuple[Path, int, int]]) -> None:
    # Fail closed if objects change between planning and apply.
    for path, before, target in changes:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW |
                     (os.O_DIRECTORY if path.is_dir() else os.O_NONBLOCK))
        try:
            info = os.fstat(fd)
            if (info.st_uid != 0 or stat.S_IMODE(info.st_mode) != before or
                    (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
                raise ValueError("metadata changed since plan")
            os.fchmod(fd, target)
        finally:
            os.close(fd)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    p.add_argument("--acknowledge", default="")
    p.add_argument("--root", type=Path, default=ROOT,
                   help="alternate root for offline --check only")
    args = p.parse_args(argv)
    if args.apply:
        if args.acknowledge != ACK or args.root != ROOT:
            p.error("--apply requires canonical root and explicit acknowledgement")
        if os.geteuid() != 0:
            p.error("--apply requires root on TrueNAS")
    elif args.acknowledge:
        p.error("acknowledgement only valid with --apply")
    try:
        changes, blockers = plan(args.root)
        for path, before, after in changes:
            print(f"MODE_DRIFT: {path.relative_to(args.root)} {before:04o}->{after:04o}")
        for message in blockers:
            print("BLOCKED: " + message)
        print(f"Summary: mode_changes={len(changes)} blockers={len(blockers)}")
        if blockers:
            print("NO_MUTATIONS: resolve symlinks / non-root ownership / special files individually")
            return 2
        if args.apply:
            apply_changes(args.root, changes)
            print(f"APPLIED: {len(changes)} mode-only changes; uid/gid preserved")
        else:
            print("READ_ONLY: audit complete; no mode or ownership changes")
        return 0 if not changes or args.apply else 1
    except (OSError, ValueError) as exc:
        print("BLOCKED: mode inspection failed: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
