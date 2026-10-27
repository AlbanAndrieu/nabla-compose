#!/usr/bin/env python3
"""Read-only classifier for a private TrueNAS FastAPI Docker build log.

Never prints log contents, paths from log records, credentials, URLs, or
arbitrary error messages. Fails closed on unsafe/large/symlinked files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
from typing import NamedTuple


class Rule(NamedTuple):
    code: str
    regex: str
    next_check: str


# Priority matters: terminal resource failures outrank generic BuildKit errors.
RULES = (
    Rule("disk_full", r"no space left on device|ENOSPC|write .* no space", "inspect_truenas_zfs_available_and_docker_storage"),
    Rule("oom_or_killed", r"out of memory|oom.?kill|cannot allocate memory|exit code: 137|signal: killed|killed process [0-9]+", "inspect_truenas_memory_pressure_and_oom_readonly"),
    Rule("buildkit_frontend_crash", r"frontend grpc server closed unexpectedly|rpc error: code = unavailable|failed to receive status", "inspect_buildkit_health_and_memory_before_retry"),
    Rule("network_dns", r"temporary failure in name resolution|could not resolve host|no such host|name or service not known", "check_docker_builder_dns_without_rebuild"),
    Rule("network_timeout", r"tls handshake timeout|i/o timeout|connection timed out|operation timed out|network is unreachable", "check_builder_registry_transport_and_proxy"),
    Rule("registry_auth", r"401 unauthorized|403 forbidden|denied: requested access|authentication required", "check_registry_auth_privately_without_printing_token"),
    Rule("tls_certificate", r"certificate verify failed|x509: certificate|certificate signed by unknown authority", "check_registry_ca_and_container_clock"),
    Rule("uv_dependency", r"uv sync|failed to resolve dependencies|no solution found|lockfile needs to be updated|package metadata", "check_uv_lock_and_dependency_build_offline"),
    Rule("apt_package", r"apt-get .* failed|unable to locate package|failed to fetch .*debian|dpkg: error", "check_builder_apt_cache_and_debian_mirror"),
    Rule("dockerfile_copy", r"failed to calculate checksum|not found: .*dockerfile|failed to compute cache key", "check_docker_context_submodules_and_ignore_rules"),
    Rule("builder_unavailable", r"cannot connect to the docker daemon|failed to solve: rpc error|context canceled|buildkit.*unavailable", "inspect_docker_builder_readonly"),
)
LOG_NAME = re.compile(r"tmp[.][A-Za-z0-9]{6,20}\Z")
MAX_FILE_BYTES = 20 * 1024 * 1024
READ_TAIL_BYTES = 1024 * 1024
VALID_CODES = frozenset(rule.code for rule in RULES)


def private_tail(path: str) -> tuple[str | None, str]:
    """Open only /tmp/mktemp logs with no symlinks or permission drift."""
    candidate = Path(path)
    if (not candidate.is_absolute() or candidate.parent != Path("/tmp")
            or not LOG_NAME.fullmatch(candidate.name)):
        return None, "unsafe_log_path"
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError:
        return None, "log_unavailable_or_unauthorized"
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            return None, "unsafe_log_type"
        if (stat.S_IMODE(metadata.st_mode) & 0o077) != 0:
            return None, "unsafe_log_permissions"
        if metadata.st_uid not in (0, os.geteuid()):
            return None, "unsafe_log_owner"
        if metadata.st_size > MAX_FILE_BYTES:
            return None, "log_too_large"
        os.lseek(fd, max(0, metadata.st_size - READ_TAIL_BYTES), os.SEEK_SET)
        data = os.read(fd, READ_TAIL_BYTES)
        # Read-only: never return original content to caller.
        return data.decode("utf-8", errors="replace"), "accepted"
    finally:
        os.close(fd)


def classify(content: str) -> dict[str, object]:
    """Return only fixed error categories; all free-form text is discarded."""
    # Truncate before regex, to protect the diagnostic itself under pressure.
    content = content[-READ_TAIL_BYTES:]
    matches = [
        {"state": rule.code, "next_check": rule.next_check}
        for rule in RULES if re.search(rule.regex, content, flags=re.I)
    ]
    if not matches:
        return {
            "state": "unclassified_build_failure",
            "next_check": "inspect_private_build_log_locally_without_sharing",
            "matched_categories": [],
        }
    # Multiple conditions can co-occur, but never include actual log text.
    return {
        "state": matches[0]["state"],
        "next_check": matches[0]["next_check"],
        "matched_categories": [item["state"] for item in matches[:6]],
    }


def check(path: str) -> dict[str, object]:
    content, status = private_tail(path)
    if content is None:
        return {
            "component": "fastapi_truenas_build",
            "state": status,
            "next_check": "verify_private_log_path_owner_and_mode_on_truenas",
            "raw_log_printed": False,
        }
    result = classify(content)
    return {"component": "fastapi_truenas_build",
            "raw_log_printed": False, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--log", required=True, help="Private /tmp/tmp.* from failed build")
    args = parser.parse_args(argv)
    print(json.dumps(check(args.log), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
