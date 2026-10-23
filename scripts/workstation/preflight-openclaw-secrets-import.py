#!/usr/bin/env python3
"""Safely preflight a selected OpenClaw shared-store dotenv import.

Read-only. No secrets are written, printed, copied, or passed as CLI values.
An import to the shared team store DOES NOT rewrite existing SecretRefs.
"""
import argparse
import os
from pathlib import Path
import stat
import subprocess

MAX_IMPORT_BYTES = 1024 * 1024


def preflight_file(path, root):
    """Return a fixed state without reading or logging secret material."""
    # Only a dedicated private staging directory outside source control.
    if path.parent != root or path.name.startswith(".") or path.suffix != ".env":
        return "outside_private_staging"
    if root.is_symlink() or not root.is_dir():
        return "unsafe_staging_directory"
    directory = root.stat()
    if (directory.st_uid != os.geteuid()
            or not stat.S_ISDIR(directory.st_mode)
            or directory.st_mode & 0o077):
        return "unsafe_staging_directory"
    if path.is_symlink():
        return "unsafe_file"
    file_stat = path.lstat()
    if (not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or file_stat.st_mode & 0o077
            or file_stat.st_nlink != 1
            or file_stat.st_size == 0
            or file_stat.st_size > MAX_IMPORT_BYTES):
        return "unsafe_file"
    return "private"


def preflight_import(path, timeout=60):
    """Delegate dotenv parsing and validation to the installed OpenClaw CLI."""
    try:
        outcome = subprocess.run(
            ["openclaw", "secrets", "store", "import",
             "--from", str(path), "--kind", "secret", "--scope", "team", "--dry-run"],
            stdin=subprocess.DEVNULL,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return "native_timeout"
    except OSError:
        return "cli_unavailable"
    return "native_accepted" if outcome.returncode == 0 else "native_rejected"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True,
                        help="Name of a selected, private dotenv file in the staging folder")
    args = parser.parse_args()
    staging = Path.home() / ".local/share/nabla-compose/openclaw-import"
    try:
        state = preflight_file(args.file.expanduser(), staging)
    except OSError:
        state = "missing_or_unreadable"
    print("secret_import_source=" + state)
    if state != "private":
        print("secret_import_native_dry_run=not_started")
        print("secret_import_changed=false")
        return 2
    result = preflight_import(args.file.expanduser())
    print("secret_import_native_dry_run=" + result)
    print("secret_import_store_scope=shared_team")
    print("secret_import_existing_name_collision_check=not_performed")
    print("secret_import_target_consumers_migrated=false")
    print("secret_import_config_refs_migrated=false")
    print("secret_import_changed=false")
    return 0 if result == "native_accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
