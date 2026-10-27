#!/usr/bin/env python3
"""Read-only legacy git-crypt OpenClaw migration inventory. No content publication.

Never copies legacy .openclaw files into the public nabla-compose repository.
No reads of secret values, databases, tokens, session transcripts, or Git history.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

BASE = Path.home() / "w/nabla/env/home/dotfiles/.openclaw"
# Explicit fixed inventory. Personal identity and sensitive runtime state are
# deliberately NOT enumerated/read as source data.
REVIEW = {
    "workspace/AGENTS.md": "review_nonsecret_policy",
    "workspace/SOUL.md": "review_nonsecret_policy",
    "workspace/TOOLS.md": "review_nonsecret_policy",
    "workspace/IDENTITY.md": "private_identity_do_not_publish",
    "workspace/USER.md": "private_identity_do_not_publish",
    "workspace/HEARTBEAT.md": "legacy_heartbeat_do_not_activate",
    "workspace/skills/tech-news-digest/SKILL.md": "review_upstream_skill_pin",
    "workspace/skills/caldav-calendar/SKILL.md": "review_upstream_skill_pin",
    "workspace/skills/tech-news-digest/workspace/config/tech-news-digest-sources.json": "review_private_sources",
    "workspace/skills/tech-news-digest/workspace/config/tech-news-digest-topics.json": "review_private_topics",
}
GITCRYPT_MAGIC = b"\x00GITCRYPT\x00"
MAX_METADATA_READ = len(GITCRYPT_MAGIC)


def file_state(path: Path, *, inspect_magic: bool = True) -> str:
    try:
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.geteuid():
            return "unsafe_type_or_owner"
        if s.st_mode & 0o022:
            return "unsafe_writable_permissions"
        if s.st_size == 0:
            return "empty"
        if not inspect_magic:
            return "present_not_inspected"
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            marker = os.read(fd, MAX_METADATA_READ)
        finally:
            os.close(fd)
        return "gitcrypt_locked" if marker == GITCRYPT_MAGIC else "locally_readable_review_required"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unavailable"


def inventory(root: Path) -> dict:
    # Refuse symlinks in the root; only explicit files are inspected.
    if root.is_symlink() or not root.is_dir():
        return {"migration_status": "legacy_root_unavailable",
                "secrets_copied": False, "runtime_changed": False}
    rows = []
    for name, category in REVIEW.items():
        # No content read for personal identities, private source lists, or topics.
        restricted = category in ("private_identity_do_not_publish",
                                  "review_private_sources", "review_private_topics")
        status = file_state(root / name, inspect_magic=not restricted)
        rows.append({"role": name, "policy": category, "source_status": status,
                     "auto_publish": False})
    return {
        "migration_status": "review_required_no_content_copied",
        "known_files": rows,
        "legacy_runtime_keys_or_sqlite_inspected": False,
        "secrets_copied": False, "runtime_changed": False,
        "heartbeat_reactivated": False,
        "note": "Local legacy files can be git-crypt protected; never copy to public Git without a reviewed sanitized replacement.",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", required=True)
    p.add_argument("--legacy-root", type=Path, default=BASE)
    args = p.parse_args(argv)
    result = inventory(args.legacy_root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["migration_status"] == "review_required_no_content_copied" else 2


if __name__ == "__main__":
    raise SystemExit(main())
