#!/usr/bin/env python3
"""Stage non-secret DefectDojo runtime .env without touching live .env.secrets.

Never create passwords here; see the canonical Vaultwarden manifest.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

TARGET = Path("/mnt/cpool/secrets/runtime/defectdojo/.env")
CONTENTS = "# Metadata only; do not insert secrets.\nDD_ADMIN_MAIL=admin@defectdojo.local\nDD_INITIALIZE=true\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("choose --check or --apply")
    if args.check:
        print("CHECK: root:root 0600 runtime .env; no secret values; no mutation")
        return 0
    if os.geteuid() != 0:
        parser.error("--apply requires TrueNAS root")
    parent = TARGET.parent
    if not parent.is_dir() or parent.is_symlink() or (parent.stat().st_mode & 0o777) != 0o700:
        parser.error("runtime secret directory must already exist with mode 0700")
    if TARGET.is_symlink():
        parser.error("refusing symlink target")
    if TARGET.exists():
        if TARGET.read_text(encoding="utf-8") != CONTENTS:
            parser.error("runtime .env already differs; no overwrite")
        if (TARGET.stat().st_mode & 0o777) != 0o600:
            parser.error("existing runtime .env must be 0600")
        print("OK: nonsecret runtime file already present")
        return 0
    fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(CONTENTS)
    print("OK: nonsecret runtime .env staged; .env.secrets remains Vaultwarden-owned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
