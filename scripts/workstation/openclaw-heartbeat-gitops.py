#!/usr/bin/env python3
"""Explicit and secure GitOps deployment for workstation heartbeat policy."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from datetime import datetime, timezone

SOURCE = Path(__file__).resolve().parents[2] / "apps/openclaw/workstation/HEARTBEAT.md"
BRIEFING_SOURCE = SOURCE.with_name("MORNING_BRIEFING.md")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validated_file(path: Path, allow_missing: bool = False) -> bytes | None:
    if path.is_symlink():
        raise ValueError("symlink_refused")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    if not stat.S_ISREG(mode):
        raise ValueError("not_regular_file")
    return path.read_bytes()


def operate(action: str, home: Path, source: Path = SOURCE, *,
            target_name: str = "HEARTBEAT.md", create_missing: bool = False) -> str:
    source_bytes = validated_file(source)
    assert source_bytes is not None
    if target_name not in ("HEARTBEAT.md", "MORNING_BRIEFING.md"):
        raise ValueError("unsupported_target_name")
    target = home / "workspace" / target_name
    if target.parent.is_symlink():
        raise ValueError("workspace_symlink_refused")
    current = validated_file(target, allow_missing=True)
    if action == "check":
        return ("matching" if current == source_bytes else "different") + (
            f" source_sha256={digest(source_bytes)}"
            + (f" target_sha256={digest(current)}" if current is not None else " target=absent")
        )
    if current is None and (not create_missing or action == "backup"):
        raise ValueError("current_heartbeat_missing_refuse_unsafe_replace")
    backup_dir = home / "backups/heartbeat-gitops"
    if backup_dir.is_symlink():
        raise ValueError("backup_directory_symlink_refused")
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = (backup_dir / f"{target.stem}.{timestamp}.{digest(current)[:12]}.md"
              if current is not None else None)
    if backup is not None:
        try:
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            # Same-second backup of unchanged bytes: retain existing snapshot.
            if validated_file(backup) != current:
                raise ValueError("backup_collision_different_content") from None
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(current)
                stream.flush()
                os.fsync(stream.fileno())
    if action == "backup":
        return f"backup={backup} sha256={digest(current)}"
    fd, temp_name = tempfile.mkstemp(prefix=".heartbeat-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(source_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        # Re-check target before replacing to avoid a silent concurrent edit.
        if validated_file(target, allow_missing=create_missing) != current:
            raise ValueError("heartbeat_changed_during_apply")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return f"applied_sha256={digest(source_bytes)} backup={backup if backup is not None else 'none_created_new_file'}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--backup", action="store_true")
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--briefing-check", action="store_true")
    actions.add_argument("--briefing-apply", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.home() / ".openclaw")
    args = parser.parse_args()
    action = "check" if args.check or args.briefing_check else "backup" if args.backup else "apply"
    try:
        if args.briefing_check or args.briefing_apply:
            print(operate(action, args.root, BRIEFING_SOURCE,
                          target_name="MORNING_BRIEFING.md", create_missing=True))
        else:
            print(operate(action, args.root))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ERROR: {type(exc).__name__}; operation not completed") from None


if __name__ == "__main__":
    main()
