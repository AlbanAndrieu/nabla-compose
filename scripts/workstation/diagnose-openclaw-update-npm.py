#!/usr/bin/env python3
"""Classify the local OpenClaw npm update failure without exposing npm logs.

Read-only, offline, and safe for repeated Workstation execution.
Does not run npm install, change the prefix, restart the Gateway, or
display user paths, registry URLs, arguments, package contents, or tokens.
"""
import argparse
from collections import Counter, deque
import os
from pathlib import Path
import re
import stat
import subprocess

LOG_BASENAME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}_\d{3}Z-debug-0\.log\Z")
VERSION = re.compile(r"v?\d+\.\d+\.\d+(?:[-+][\w.]+)?\Z")
ERROR_CODE = re.compile(r"\b(?:EACCES|EPERM|EEXIST|ENOTEMPTY|EBUSY|EBADENGINE|ETARGET|E404|EINTEGRITY|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|EUNSUPPORTEDPROTOCOL|ERESOLVE|EISDIR)\b", re.I)
CATEGORIES = {
    "permission": ("EACCES", "EPERM"),
    "install_collision": ("EEXIST", "ENOTEMPTY", "EBUSY", "EISDIR"),
    "runtime_engine": ("EBADENGINE",),
    "registry_or_integrity": ("ETARGET", "E404", "EINTEGRITY", "EUNSUPPORTEDPROTOCOL"),
    "network": ("ECONNRESET", "ETIMEDOUT", "ENOTFOUND", "EAI_AGAIN"),
    "dependency_resolution": ("ERESOLVE",),
}
HINTS = (
    ("build_toolchain", ("node-gyp", "gyp ERR!", "make failed", "cmake failed")),
    ("memory_pressure", ("ENOSPC", "out of memory", "heap out of memory")),
)


def safe_log(path, home):
    """Allow only a private regular npm debug log from ~/.npm/_logs."""
    if path.parent != home / ".npm/_logs" or not LOG_BASENAME.fullmatch(path.name):
        return False
    for directory in (home / ".npm", home / ".npm/_logs"):
        try:
            st = directory.lstat()
            if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o022):
                return False
        except OSError:
            return False
    try:
        s = path.lstat()
        return (stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and s.st_nlink == 1 and s.st_size <= 10 * 1024 * 1024)
    except OSError:
        return False


def choose_log(home, requested):
    folder = home / ".npm/_logs"
    if requested:
        possible = folder / requested
        return possible if safe_log(possible, home) else None
    try:
        options = [p for p in folder.iterdir() if safe_log(p, home)]
    except OSError:
        return None
    return max(options, key=lambda p: p.name) if options else None


def classify(lines):
    """Return only controlled labels and counts; never return source lines."""
    codes = Counter()
    extras = Counter()
    for line in lines:
        # The npm debug tail contains personal paths and often tokens.
        # Never print/log/return the line itself.
        for match in ERROR_CODE.findall(line):
            codes[match.upper()] += 1
        lower = line.lower()
        for name, needles in HINTS:
            if any(value.lower() in lower for value in needles):
                extras[name] += 1
    tags = {name for name, group in CATEGORIES.items()
            if any(codes[code] for code in group)}
    tags.update(k for k, value in extras.items() if value)
    if not tags:
        tags.add("unknown")
    return sorted(tags), codes


def installed_version(command):
    try:
        p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           check=False, timeout=8, text=True)
        result = p.stdout.strip().splitlines()
        if p.returncode == 0 and len(result) == 1:
            raw = result[0]
            if VERSION.fullmatch(raw):
                return raw.lstrip("v")
            # OpenClaw prints 'OpenClaw 2026.9.5 (build)' not bare semver.
            match = re.fullmatch(r"OpenClaw (\d+\.\d+\.\d+)(?: \([^\r\n]{1,100}\))?", raw)
            if match:
                return match.group(1)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    return "unavailable"


def node_target_compatibility(version):
    """Pinned OpenClaw 2026.10.7 Node engine floor; no npm/network access."""
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return "unverified"
    major, minor, patch = map(int, version.split("."))
    if major == 24:
        return "compatible" if (minor, patch) >= (22, 1) else "below_floor"
    if major == 26:
        return "compatible" if (minor, patch) >= (12, 1) else "below_floor"
    return "unsupported_line"


def npm_prefix_posture(home):
    try:
        p = subprocess.run(["npm", "prefix", "-g"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, check=False, timeout=8, text=True)
        if p.returncode:
            return "unavailable", "unverified"
        prefix = Path(p.stdout.strip())
        if not prefix.is_absolute():
            return "unavailable", "unverified"
        try:
            local = prefix.resolve().is_relative_to(home.resolve())
        except (OSError, ValueError):
            local = False
        # npm installs in its prefix, whose parent ownership alone does not
        # establish package-manager correctness.
        return ("within_home" if local else "outside_home",
                "likely_writable" if os.access(prefix, os.W_OK) else "not_writable_or_missing")
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return "unavailable", "unverified"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-name", default=None, help="npm debug log BASENAME only")
    args = parser.parse_args(argv)
    home = Path.home()
    selected = choose_log(home, args.log_name)
    print("openclaw_update_triage=read_only")
    node = installed_version(["node", "--version"])
    print("node_version=" + node)
    print("openclaw_target_version=2026.10.7")
    print("target_node_floor=24.22.1_or_26.12.1")
    print("target_node_compatibility=" + node_target_compatibility(node))
    print("npm_version=" + installed_version(["npm", "--version"]))
    print("openclaw_version=" + installed_version(["openclaw", "--version"]))
    location, writable = npm_prefix_posture(home)
    print("npm_global_prefix_scope=" + location)
    print("npm_global_prefix_writability=" + writable)
    if selected is None:
        print("npm_debug_log=missing_or_unsafe")
        print("npm_error_category=unverified")
        print("update_attempted=false")
        return 2
    try:
        with selected.open("r", encoding="utf-8", errors="replace") as stream:
            lines = deque(stream, maxlen=3000)
        tags, codes = classify(lines)
    except OSError:
        print("npm_debug_log=unavailable")
        return 2
    print("npm_debug_log=inspected")
    # Date is derived from the validated filename only; no local path emitted.
    print("npm_debug_log_timestamp=" + selected.name[:23])
    print("npm_error_category=" + ",".join(tags))
    print("npm_known_error_code_count=" + str(sum(codes.values())))
    print("npm_raw_log_exposed=false")
    print("update_attempted=false")
    print("gateway_changed=false")
    return 0 if tags != ["unknown"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
