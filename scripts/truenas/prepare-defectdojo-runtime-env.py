#!/usr/bin/env python3
"""Stage/inspect non-secret DefectDojo runtime metadata without touching secrets.

--check is a no-mutation portable policy check.
--inspect attests the real TrueNAS path. --apply normalizes metadata only.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

TARGET = Path("/mnt/cpool/secrets/runtime/defectdojo/.env")
CONTENTS = "# Metadata only; do not insert secrets.\nDD_ADMIN_MAIL=nabla@defectdojo.local\nDD_INITIALIZE=true\n"
EXPECTED = {"DD_ADMIN_MAIL": "nabla@defectdojo.local", "DD_INITIALIZE": "true"}


def inspect(path: Path = TARGET) -> str:
    if path.is_symlink():
        return "SYMLINK_REFUSED"
    if not path.is_file():
        return "FILE_MISSING"
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return "FILE_TYPE_INVALID"
    if info.st_size > 4096:
        return "FILE_OVERSIZED"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeError, OSError):
        return "FILE_UNREADABLE"
    found: dict[str, str] = {}
    for line in lines:
        part = line.strip()
        if not part or part.startswith("#"):
            continue
        if "=" not in part:
            return "METADATA_INVALID"
        key, value = part.split("=", 1)
        key = key.strip()
        if key not in EXPECTED or key in found:
            return "METADATA_INVALID"
        found[key] = value.strip()
    if found != EXPECTED:
        return "METADATA_INVALID"
    if (info.st_uid != 0 or info.st_gid != 0 or
            stat.S_IMODE(info.st_mode) != 0o600):
        return "METADATA_PERMISSIONS_INVALID"
    return "READY"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check:
        print("CHECK: root:root 0600 runtime .env; metadata only; no mutation")
        return 0
    if os.geteuid() != 0:
        parser.error("--inspect/--apply requires TrueNAS root")
    if not TARGET.parent.is_dir() or TARGET.parent.is_symlink() or (
            stat.S_IMODE(TARGET.parent.stat().st_mode) != 0o700):
        print("BLOCKED: unsafe runtime directory")
        return 2
    state = inspect()
    if args.inspect:
        print("defectdojo_runtime_env=" + state)
        return 0 if state == "READY" else 2
    if state == "READY":
        print("OK: non-secret runtime env already ready")
        return 0
    if state == "FILE_MISSING":
        fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(CONTENTS)
        os.chown(TARGET, 0, 0)
    elif state == "METADATA_PERMISSIONS_INVALID":
        # Operators may have copied .env.example with their own uid/gid.
        # Only this exact, non-secret, already validated metadata file is fixed.
        os.chown(TARGET, 0, 0, follow_symlinks=False)
        TARGET.chmod(0o600, follow_symlinks=False)
    else:
        print("BLOCKED: " + state + "; no overwrite")
        return 2
    state = inspect()
    print("defectdojo_runtime_env=" + state)
    return 0 if state == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
