#!/usr/bin/env python3
"""Read the declared OpenClaw memory minScore without exposing other config values."""
import argparse
import json
import math
import os
from pathlib import Path
import stat

MAX_CONFIG_BYTES = 4 * 1024 * 1024
# Exact upstream tag v2026.9.5: src/agents/memory-search.ts.
# Informational only; never claim a runtime version was checked by this script.
V2026_9_5_DEFAULT = 0.35


def load_private_config(path):
    """No symlinks, group-readable files, hardlinks or unbounded reads."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > MAX_CONFIG_BYTES
                or info.st_nlink != 1):
            raise ValueError("unsafe_config")
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(MAX_CONFIG_BYTES + 1)
        if len(payload) > MAX_CONFIG_BYTES:
            raise ValueError("oversized_config")
        return json.loads(payload)
    finally:
        os.close(fd)


def read_explicit_score(source):
    """Status/value pair; do not interpret vendor defaults as explicit."""
    if not isinstance(source, dict):
        return "invalid", None
    memory = source.get("memory", {})
    if not isinstance(memory, dict):
        return "invalid", None
    search = memory.get("search", {})
    if not isinstance(search, dict):
        return "invalid", None
    query = search.get("query", {})
    if not isinstance(query, dict):
        return "invalid", None
    if "minScore" not in query:
        return "not_explicit", None
    score = query["minScore"]
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        return "invalid", None
    return "explicit", score


def agent_entry(root, agent):
    """Follow v2026.9.5 agent roster entries/list shapes; fail closed."""
    agents = root.get("agents", {})
    if not isinstance(agents, dict):
        return None
    entries = agents.get("entries")
    if entries is not None:
        if not isinstance(entries, dict):
            return None
        entry = entries.get(agent)
        return entry if isinstance(entry, dict) else None
    roster = agents.get("list")
    if roster is not None:
        if not isinstance(roster, list):
            return None
        matches = [item for item in roster
                   if isinstance(item, dict) and item.get("id") == agent]
        return matches[0] if len(matches) == 1 else None
    return None


def inspect(path, agent=None):
    """Return a bounded status/value; never print or return private config."""
    root = load_private_config(path)
    status, score = read_explicit_score(root)
    if status == "invalid" or agent is None:
        return status, score
    if not isinstance(root, dict):
        return "invalid", None
    entry = agent_entry(root, agent)
    if entry is None:
        return "agent_unresolved", None
    agent_status, agent_score = read_explicit_score(entry)
    if agent_status == "invalid":
        return "invalid", None
    if agent_status == "explicit":
        return "agent_explicit", agent_score
    if status == "explicit":
        return "inherited_global", score
    return "upstream_default", V2026_9_5_DEFAULT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw" / "openclaw.json")
    parser.add_argument("--agent", choices=("main", "cron"),
                        help="Inspect per-agent override and global/default precedence")
    args = parser.parse_args()
    try:
        status, score = inspect(args.config, args.agent)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        status, score = "blocked", None
    if args.agent:
        print("memory_min_score_agent=" + args.agent)
    print("memory_min_score_status=" + status)
    if status in ("explicit", "agent_explicit", "inherited_global", "upstream_default"):
        print(f"memory_min_score_value={score:.3f}")
    else:
        print("memory_min_score_value=not_established")
    print(f"memory_min_score_reference_default_2026_9_5={V2026_9_5_DEFAULT:.3f}")
    print("memory_min_score_runtime_version_verified=false")
    print("configuration_changed=false")
    return 0 if status in ("explicit", "not_explicit", "agent_explicit",
                           "inherited_global", "upstream_default") else 2


if __name__ == "__main__":
    raise SystemExit(main())
