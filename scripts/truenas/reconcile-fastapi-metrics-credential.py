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
        matches.append(raw)
    if not matches:
        raise ValueError("metrics_key_missing")
    if len(matches) != 1:
        raise ValueError("metrics_key_duplicated")
    if not KEY_RE.fullmatch(matches[0]):
        raise ValueError("metrics_key_format_invalid")
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


SOURCE_STATES = frozenset({
    "source_file_missing",
    "source_metadata_unavailable",
    "source_symlink_refused",
    "source_file_not_regular",
    "source_hardlink_refused",
    "source_owner_not_root",
    "source_permissions_insecure",
    "source_file_empty_or_oversized",
    "source_read_unavailable",
    "source_encoding_invalid",
    "source_key_missing",
    "source_key_duplicated",
    "source_key_format_invalid",
})

# Only stable remediation codes. Never print path metadata or key values.
NEXT_CHECK = {
    "source_file_missing": "verify_canonical_sample_env_file_exists_on_truenas",
    "source_metadata_unavailable": "verify_private_sample_env_file_access",
    "source_symlink_refused": "replace_symlink_using_approved_secret_materialization",
    "source_file_not_regular": "verify_sample_env_is_regular_file",
    "source_hardlink_refused": "verify_private_sample_env_is_not_hardlinked",
    "source_owner_not_root": "review_source_secret_file_owner_before_chown",
    "source_permissions_insecure": "review_source_secret_mode_without_dumping_file",
    "source_file_empty_or_oversized": "review_secret_file_size_without_dumping_file",
    "source_read_unavailable": "verify_root_can_read_canonical_sample_env",
    "source_encoding_invalid": "verify_sample_env_is_valid_utf8_without_dumping_it",
    "source_key_missing": "verify_metrics_scrape_key_name_in_sample_env",
    "source_key_duplicated": "deduplicate_metrics_scrape_key_declarations",
    "source_key_format_invalid": "verify_metrics_scrape_key_is_64_hex_characters",
    "credential_not_installed": "install_credential_with_explicit_operator_approval",
    "credential_mismatch": "reconcile_existing_prometheus_scrape_key_privately",
    "credential_ready": "verify_fastapi_container_loaded_key_and_prometheus_mount",
    "destination_directory_unavailable": "verify_prometheus_secret_directory_exists_and_is_private",
    "destination_directory_insecure": "review_prometheus_secret_directory_ownership_and_mode",
    "destination_symlink_refused": "refuse_symlinked_prometheus_scrape_credential",
    "destination_metadata_invalid": "review_prometheus_scrape_credential_owner_and_mode",
    "destination_key_invalid": "verify_prometheus_scrape_key_file_format",
    "destination_unreadable": "verify_prometheus_secret_file_access",
    "install_blocked": "recheck_private_source_and_destination_preflight",
}


def inspect_source(source: Path, *, require_root: bool = True) -> tuple[str, bytes | None]:
    """Classify source failure without exposing private file contents or metadata."""
    try:
        info = source.lstat()
    except FileNotFoundError:
        return "source_file_missing", None
    except OSError:
        return "source_metadata_unavailable", None
    if stat.S_ISLNK(info.st_mode):
        return "source_symlink_refused", None
    if not stat.S_ISREG(info.st_mode):
        return "source_file_not_regular", None
    if info.st_nlink != 1:
        return "source_hardlink_refused", None
    if require_root and info.st_uid != 0:
        return "source_owner_not_root", None
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o026 or not mode & 0o400:
        return "source_permissions_insecure", None
    if not 1 <= info.st_size <= MAX_SOURCE_BYTES:
        return "source_file_empty_or_oversized", None
    try:
        data = secure_read(source, MAX_SOURCE_BYTES, require_root=require_root)
    except (OSError, ValueError):
        return "source_read_unavailable", None
    try:
        return "source_ready", parse_key(data)
    except UnicodeError:
        return "source_encoding_invalid", None
    except ValueError as exc:
        error = str(exc)
        category = {
            "metrics_key_missing": "source_key_missing",
            "metrics_key_duplicated": "source_key_duplicated",
            "metrics_key_format_invalid": "source_key_format_invalid",
        }.get(error, "source_key_format_invalid")
        return category, None


def inspect(source: Path = SOURCE, dest: Path = DEST, *, require_root: bool = True) -> str:
    """Return a fixed category; never disclose a token or its fingerprint."""
    state, token = inspect_source(source, require_root=require_root)
    if state != "source_ready":
        return state
    assert token is not None  # Satisfies the internal source-status contract.

    if dest.parent.is_symlink() or not dest.parent.is_dir():
        return "destination_directory_unavailable"
    try:
        parent = dest.parent.stat(follow_symlinks=False)
        if (
            (require_root and (parent.st_uid != 0 or parent.st_gid != EXPECTED_GID
                               or not stat.S_IMODE(parent.st_mode) & 0o010))
            or stat.S_IMODE(parent.st_mode) & 0o022
        ):
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


def prepare_destination_directory(dest: Path) -> None:
    """Create only the missing private scrape-secret directory on approved apply."""
    parent = dest.parent
    base = parent.parent
    if parent.is_symlink() or parent.exists():
        raise ValueError("destination_directory_not_missing")
    # Never create a new parent tree and never follow an existing parent symlink.
    if base.is_symlink() or not base.is_dir():
        raise ValueError("destination_parent_unavailable")
    base_info = base.stat(follow_symlinks=False)
    if (base_info.st_uid != 0
            or stat.S_IMODE(base_info.st_mode) & 0o022):
        raise ValueError("destination_parent_insecure")
    os.mkdir(parent, 0o750)
    os.chown(parent, 0, EXPECTED_GID)
    os.chmod(parent, 0o750)


def install(source: Path = SOURCE, dest: Path = DEST) -> str:
    """Atomically install the credential with uid 0, gid 568, mode 0640."""
    status = inspect(source, dest)
    if status == "destination_directory_unavailable":
        # The file bind has create_host_path=false: the destination directory
        # must be provisioned before Prometheus can start. Never make the
        # missing secret itself, and never create an unbounded parent tree.
        prepare_destination_directory(dest)
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
        "next_check": NEXT_CHECK.get(state, "review_private_diagnostic_preflight"),
    }, sort_keys=True))
    return 0 if state == "credential_ready" else (
        1 if state in {"credential_not_installed", "credential_mismatch"} else 2
    )


if __name__ == "__main__":
    sys.exit(main())
