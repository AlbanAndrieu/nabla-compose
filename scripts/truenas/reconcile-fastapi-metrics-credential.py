#!/usr/bin/env python3
"""Safely materialize FastAPI's dedicated metrics key for Prometheus on TrueNAS.

--check never writes. --apply requires an explicit acknowledgement.
Read exactly one METRICS_SCRAPE_KEY from the existing private sample dotenv.
Never display, hash, export, or put secret material on the command line.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

SOURCE = Path("/mnt/cpool/secrets/runtime/sample/.env.secrets")
DEST = Path("/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key")
ACK = "I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL"
EXPECTED_GID = 568
MAX_SOURCE_BYTES = 256 * 1024
KEY_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


def parse_key(data: bytes) -> bytes:
    """Parse an unambiguous 256-bit hex key from a Docker dotenv file."""
    text = data.decode("utf-8")
    matches: list[str] = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        field, _, raw = value.partition("=")
        if field.strip() != "METRICS_SCRAPE_KEY":
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] in {'"', "'"} and raw[-1] == raw[0]:
            raw = raw[1:-1]
        if not KEY_RE.fullmatch(raw):
            raise ValueError("metrics_key_format_invalid")
        matches.append(raw)
    if len(matches) != 1:
        raise ValueError("metrics_key_missing_or_duplicated")
    return matches[0].encode("ascii")


def secure_read(path: Path, limit: int, *, require_root: bool) -> bytes:
    """Read one regular, private, non-hardlinked file without following links."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (require_root and info.st_uid != 0)
            or mode & 0o022
            or mode & 0o004
            or info.st_size < 1
            or info.st_size > limit
        ):
            raise ValueError("private_file_metadata_invalid")
        value = os.read(fd, limit + 1)
        if len(value) > limit:
            raise ValueError("private_file_too_large")
        return value
    finally:
        os.close(fd)


def inspect(source: Path = SOURCE, dest: Path = DEST, *, require_root: bool = True) -> str:
    """Return a fixed category; never disclose a token or its fingerprint."""
    try:
        token = parse_key(secure_read(source, MAX_SOURCE_BYTES, require_root=require_root))
    except (OSError, UnicodeError, ValueError):
        return "source_missing_insecure_or_invalid"

    if dest.parent.is_symlink() or not dest.parent.is_dir():
        return "destination_directory_unavailable"
    try:
        parent = dest.parent.stat(follow_symlinks=False)
        if (require_root and parent.st_uid != 0) or stat.S_IMODE(parent.st_mode) & 0o022:
            return "destination_directory_insecure"
        if dest.is_symlink():
            return "destination_symlink_refused"
        info = dest.stat(follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or (require_root and (info.st_uid != 0 or info.st_gid != EXPECTED_GID))
                or stat.S_IMODE(info.st_mode) != 0o640):
            return "destination_metadata_invalid"
        installed = secure_read(dest, 128, require_root=require_root).strip()
        if not KEY_RE.fullmatch(installed.decode("ascii")):
            return "destination_key_invalid"
        return ("credential_ready" if hmac.compare_digest(token, installed)
                else "credential_mismatch")
    except FileNotFoundError:
        return "credential_not_installed"
    except (OSError, ValueError, UnicodeError):
        return "destination_unreadable"


def install(source: Path = SOURCE, dest: Path = DEST) -> str:
    """Atomically install the credential with uid 0, gid 568, mode 0640."""
    status = inspect(source, dest)
    if status == "credential_ready":
        return status
    if status not in {"credential_not_installed", "credential_mismatch"}:
        raise ValueError("preflight_blocked")
    token = parse_key(secure_read(source, MAX_SOURCE_BYTES, require_root=True))
    temporary: str | None = None
    descriptor = -1
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fastapi-metrics.", dir=str(dest.parent)
        )
        os.fchown(descriptor, 0, EXPECTED_GID)
        os.fchmod(descriptor, 0o640)
        os.write(descriptor, token + b"\n")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            raise ValueError("destination_changed_during_install")
        os.replace(temporary, dest)
        temporary = None
    finally:
        if descriptor != -1:
            os.close(descriptor)
        if temporary:
            os.unlink(temporary)
    if inspect(source, dest) != "credential_ready":
        raise ValueError("post_install_verification_failed")
    return "credential_ready"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge", default="")
    args = parser.parse_args(argv)
    if args.apply:
        if args.acknowledge != ACK or os.geteuid() != 0:
            parser.error("--apply requires sudo and explicit acknowledgement")
    elif args.acknowledge:
        parser.error("--acknowledge is only valid with --apply")
    try:
        state = install() if args.apply else inspect()
    except (OSError, ValueError):
        state = "install_blocked"
    # No file contents, fingerprints, secret paths or raw exceptions.
    print(json.dumps({
        "component": "fastapi_sample_prometheus_scrape",
        "mode": "apply" if args.apply else "check",
        "state": state,
        "credential_ready": state == "credential_ready",
    }, sort_keys=True))
    return 0 if state == "credential_ready" else (
        1 if state in {"credential_not_installed", "credential_mismatch"} else 2
    )


if __name__ == "__main__":
    sys.exit(main())
