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
    Rule("uv_dependency", r"uv sync[^\r\n]{0,200}(?:failed|error|exit code)|failed to resolve dependencies|no solution found|lockfile needs to be updated|(?:failed|error)[^\r\n]{0,100}package metadata", "check_uv_lock_and_dependency_build_offline"),
    Rule("apt_package", r"apt-get .* failed|unable to locate package|failed to fetch .*debian|dpkg: error", "check_builder_apt_cache_and_debian_mirror"),
    Rule("dockerfile_copy", r"failed to calculate checksum|not found: .*dockerfile|failed to compute cache key", "check_docker_context_submodules_and_ignore_rules"),
    Rule("builder_unavailable", r"cannot connect to the docker daemon|failed to solve: rpc error|context canceled|buildkit.*unavailable", "inspect_docker_builder_readonly"),
    Rule("filesystem_permissions", r"permission denied|operation not permitted|read-only file system|\bEACCES\b|\bEPERM\b", "inspect_builder_mount_permissions_readonly"),
    Rule("dependency_fetch", r"failed to download|failed to fetch|failed to get|download failed|failed to connect to|connection reset by peer", "inspect_package_mirror_or_registry_connectivity"),
    Rule("build_step_nonzero", r"(?:failed to solve: )?process [^\r\n]{0,1024} did not complete successfully|executor failed running|process did not complete successfully|exit status [1-9][0-9]*", "inspect_failed_build_step_privately"),
    Rule("dockerfile_missing", r"failed to read dockerfile|open dockerfile: no such file or directory|cannot locate specified dockerfile", "check_compose_dockerfile_path_readonly"),
    Rule("dockerfile_parse", r"dockerfile parse error|unknown instruction:|failed to parse dockerfile", "check_dockerfile_syntax_offline"),
    Rule("base_image_metadata", r"failed to resolve source metadata|failed to authorize:|failed to fetch anonymous token|failed to do request: head", "inspect_base_image_metadata_and_registry_readonly"),
    Rule("build_context_invalid", r"unable to prepare context|failed to read context|failed to load build context|failed to walk", "inspect_compose_build_context_readonly"),
    Rule("compose_service_invalid", r"no such service:|invalid compose project|service [^\r\n]{0,120} has neither an image nor a build context", "check_compose_target_service_readonly"),
    Rule("image_reference_invalid", r"invalid reference format|invalid tag [^\r\n]{0,120}|manifest unknown|manifest not found|pull access denied", "check_image_reference_or_manifest_readonly"),
    Rule("buildkit_cache", r"failed to load cache key|failed to export cache|failed to import cache|failed to prepare extraction snapshot", "check_builder_cache_state_readonly"),
    Rule("registry_request_failure", r"unexpected status from (?:HEAD|GET|POST|PUT) request", "inspect_registry_request_status_and_image_cache_readonly"),
    Rule("buildkit_generic_failure", r"failed to solve:|error response from daemon:|^#[0-9]{1,5} ERROR:|^ERROR: failed to build", "inspect_buildkit_failure_privately"),
)
LOG_NAME = re.compile(r"tmp[.][A-Za-z0-9_-]{6,20}\Z")
MAX_FILE_BYTES = 20 * 1024 * 1024
READ_TAIL_BYTES = 4 * 1024 * 1024
VALID_CODES = frozenset(rule.code for rule in RULES)


def allowed_log_owners() -> set[int]:
    """Authorize root/current UID and the original sudo invoker, not arbitrary users."""
    euid = os.geteuid()
    owners = {0, euid}
    if euid == 0:
        sudo_uid = os.environ.get("SUDO_UID", "")
        # sudo provides SUDO_UID for the caller; reject malformed/out-of-range
        # values and never trust it in an unprivileged process.
        if re.fullmatch(r"[0-9]{1,10}", sudo_uid):
            original_uid = int(sudo_uid)
            if 0 < original_uid < 2**32:
                owners.add(original_uid)
    return owners


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
        if metadata.st_uid not in allowed_log_owners():
            return None, "unsafe_log_owner"
        if metadata.st_size > MAX_FILE_BYTES:
            return None, "log_too_large"
        os.lseek(fd, max(0, metadata.st_size - READ_TAIL_BYTES), os.SEEK_SET)
        data = os.read(fd, READ_TAIL_BYTES)
        # Read-only: never return original content to caller.
        return data.decode("utf-8", errors="replace"), "accepted"
    finally:
        os.close(fd)


def buildkit_failure_context(content: str) -> dict[str, object]:
    """Fixed vocabulary only. Never expose commands, log lines, URLs or paths."""
    failure_ids = re.findall(r"(?m)^#([0-9]{1,5}) ERROR(?::|\s|$)", content)
    stage, operation = "unknown", "unknown"
    if failure_ids:
        step_id = failure_ids[-1]
        headers = re.findall(
            r"(?m)^#" + re.escape(step_id)
            + r" \[(dependency-metadata|builder|production|internal)(?: [0-9]+/[0-9]+)?\] ([^\r\n]{0,512})",
            content,
        )
        if headers:
            stage, command = headers[-1]
            if re.match(r"^load metadata for\b", command):
                operation = "image_metadata"
            elif re.search(r"\buv sync\b", command):
                operation = "uv_sync"
            elif re.search(r"\bapt-get\b", command):
                operation = "apt"
            elif re.search(r"\bnormalize-dependency-metadata\b|\bnormalize_dependency_metadata\b", command):
                operation = "dependency_metadata"
            elif re.match(r"^COPY\b", command):
                operation = "copy"
            elif re.match(r"^FROM\b", command):
                operation = "image"
            elif re.match(r"^RUN\b", command):
                operation = "other_run"
    return {
        "failure_stage": stage,
        "failure_operation": operation,
        "buildkit_failure_marker": bool(
            re.search(
                r"(?m)^#[0-9]{1,5} ERROR(?::|\s|$)|failed to solve:|^ERROR:|error response from daemon:",
                content,
                flags=re.I,
            )
        ),
    }


# Fixed public vocabulary only; matches are evaluated on the final error marker,
# not arbitrary successful build steps. Never output source words or line content.
TERMINAL_TERMS = (
    "sender", "receiver", "frontend", "solver", "vertex", "llb", "snapshotter",
    "containerd", "daemon", "buildx", "worker", "driver", "grpc", "rpc",
    "manifest", "registry", "repository", "image", "digest", "blob",
    "overlay", "mount", "snapshot", "filesystem", "directory", "path",
    "network", "proxy", "connection", "certificate", "timeout", "tls", "dns",
    "dependency", "package", "python", "git", "uv", "pip", "apt",
    "permission", "access", "unauthorized", "denied", "forbidden",
    "configuration", "compose", "dockerfile", "argument", "option",
    "invalid", "unsupported", "unknown", "missing", "unexpected",
    "cache", "export", "import", "unavailable", "closed",
    "sender", "handshake", "context", "request", "response",
)
TERMINAL_TERMS = tuple(dict.fromkeys(TERMINAL_TERMS))


def registry_request_details(terminal: str) -> dict[str, object]:
    """Expose only fixed enums and a bounded HTTP code, never registry URLs."""
    context = {
        "registry_provider": "unknown",
        "registry_image": "unknown",
        "registry_request_method": "unknown",
        "registry_http_status": None,
        "registry_http_class": "unknown",
    }
    match = re.search(
        r"\b(HEAD|GET|POST|PUT)\s+request\b", terminal, flags=re.I
    )
    if not match or not re.search(r"\bunexpected\s+status\s+from\b", terminal, re.I):
        return context
    context["registry_request_method"] = match.group(1).upper()
    # Match fixed known hosts/repositories; do not output the raw URL or tag.
    if re.search(r"(?:registry-1\.docker\.io|docker\.io)/", terminal, re.I):
        context["registry_provider"] = "docker_hub"
    elif re.search(r"ghcr\.io/", terminal, re.I):
        context["registry_provider"] = "github_container_registry"
    if re.search(r"/library/python(?:/|:)", terminal, re.I):
        context["registry_image"] = "official_python"
    # The status must follow a colon and conclude the terminal error,
    # optionally followed by a simple HTTP reason phrase.
    code_match = re.search(
        r":\s*([45][0-9]{2})(?:\s+[A-Za-z][A-Za-z -]{0,80})?\s*$",
        terminal,
    )
    if code_match:
        status = int(code_match.group(1))
        context["registry_http_status"] = status
        context["registry_http_class"] = (
            "rate_limited" if status == 429
            else "authorization" if status in (401, 403)
            else "not_found" if status == 404
            else "timeout" if status == 408
            else "upstream_or_proxy_error" if status >= 500
            else "other_client_error"
        )
    return context


def failure_shape(content: str) -> dict[str, object]:
    """Fingerprint the terminal error using *only* a finite public vocabulary."""
    lines = content[-READ_TAIL_BYTES:].splitlines()
    markers = []
    for line in lines:
        if re.search(
            r"failed to solve:|error response from daemon:|^#[0-9]{1,5} ERROR:|^ERROR:",
            line, flags=re.I,
        ):
            markers.append(line)
    terminal = markers[-1] if markers else ""
    if re.search(r"failed to solve:", terminal, flags=re.I):
        style = "solve"
    elif re.match(r"^#[0-9]{1,5} ERROR:", terminal):
        style = "numbered"
    elif re.search(r"error response from daemon:", terminal, flags=re.I):
        style = "daemon"
    elif re.match(r"^ERROR:", terminal, flags=re.I):
        style = "plain_error"
    else:
        style = "none"

    # Only code literals taken from TERMINAL_TERMS can appear in the output.
    codes = [
        term for term in TERMINAL_TERMS
        if re.search(r"\b" + re.escape(term) + r"\b", terminal, flags=re.I)
    ]
    return {
        **registry_request_details(terminal),
        "terminal_marker_style": style,
        "terminal_keyword_codes": codes,
        "error_marker_count": min(len(markers), 100),
        "numbered_error_count": min(
            sum(bool(re.match(r"^#[0-9]{1,5} ERROR:", line)) for line in lines), 100
        ),
        "buildkit_step_headers_present": any(
            bool(re.match(r"^#[0-9]{1,5} \[", line)) for line in lines
        ),
        "ansi_escapes_present": "\x1b[" in content,
        "raw_log_printed": False,
    }


def classify(content: str) -> dict[str, object]:
    """Return only fixed error categories; all free-form text is discarded."""
    # Truncate before regex, to protect the diagnostic itself under pressure.
    content = content[-READ_TAIL_BYTES:]
    context = buildkit_failure_context(content)
    matches = [
        {"state": rule.code, "next_check": rule.next_check}
        for rule in RULES if re.search(rule.regex, content, flags=re.I | re.M)
    ]
    if not matches:
        return {
            "state": "unclassified_build_failure",
            "next_check": "inspect_private_build_log_locally_without_sharing",
            "matched_categories": [],
            **context,
        }
    # Multiple conditions can co-occur, but never include actual log text.
    return {
        "state": matches[0]["state"],
        "next_check": matches[0]["next_check"],
        "matched_categories": [item["state"] for item in matches[:6]],
        **context,
    }


def check(path: str, *, include_failure_shape: bool = False) -> dict[str, object]:
    content, status = private_tail(path)
    if content is None:
        return {
            "component": "fastapi_truenas_build",
            "state": status,
            "next_check": "verify_private_log_path_owner_and_mode_on_truenas",
            "raw_log_printed": False,
        }
    result = classify(content)
    if include_failure_shape:
        result.update(failure_shape(content))
    return {"component": "fastapi_truenas_build",
            "raw_log_printed": False, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--log", required=True, help="Private /tmp/tmp.* from failed build")
    parser.add_argument("--failure-shape", action="store_true", help="Only fixed-code terminal error metadata; no raw text")
    args = parser.parse_args(argv)
    print(json.dumps(check(args.log, include_failure_shape=args.failure_shape), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
