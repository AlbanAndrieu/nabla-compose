#!/usr/bin/env python3
"""Inspect explicit OpenClaw memory minScore without showing other config values."""
import argparse
import json
import math
import os
from pathlib import Path
import stat

MAX_CONFIG_BYTES = 4 * 1024 * 1024


def inspect(path):
    """Return a fixed result. Never expose raw config, paths or exceptions."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > MAX_CONFIG_BYTES
                or info.st_nlink != 1):
            return "blocked", None
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(MAX_CONFIG_BYTES + 1)
        if len(payload) > MAX_CONFIG_BYTES:
            return "blocked", None
        root = json.loads(payload)
    finally:
        os.close(fd)
    if not isinstance(root, dict):
        return "invalid", None
    value = root.get("memory", {})
    if not isinstance(value, dict):
        return "invalid", None
    value = value.get("search", {})
    if not isinstance(value, dict):
        return "invalid", None
    value = value.get("query", {})
    if not isinstance(value, dict):
        return "invalid", None
    if "minScore" not in value:
        return "not_explicit", None
    score = value["minScore"]
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        return "invalid", None
    return "explicit", score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw" / "openclaw.json")
    args = parser.parse_args()
    try:
        status, score = inspect(args.config)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        status, score = "blocked", None
    print("memory_min_score_status=" + status)
    if status == "explicit":
        print(f"memory_min_score_value={score:.3f}")
    else:
        print("memory_min_score_value=not_established")
    print("memory_min_score_effective_default=not_established")
    print("configuration_changed=false")
    return 0 if status in ("explicit", "not_explicit") else 2


if __name__ == "__main__":
    raise SystemExit(main())
