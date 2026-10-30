#!/usr/bin/env python3
"""Read-only redacted log coverage for Workstation AND TrueNAS LiteLLM.

No tokens, API calls, SSH tunnel, secrets, remote writes or sudo escalation.
Both sources must be observed for successful coverage. Log patterns are
indicators only and cannot attribute a request to an agent or proxy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

HOST = "albandrieu@172.17.0.24"
PORT = "9922"
CONTAINERS_LOCAL = ("litellm-litellm-1", "litellm")
CONTAINER_TRUENAS = "litellm"  # apps/litellm/compose.yml container_name
MAX_BYTES = 1024 * 1024
INDICATORS = {
    "rate_limit": re.compile(r"rate.?limit|too many requests|(?<![0-9])429(?![0-9])", re.I),
    "budget": re.compile(r"budget.?exceeded|exceeded.?budget|budget.?limit", re.I),
    "auth": re.compile(r"authenticationerror|invalid.api.key|no api key passed|(?<![0-9])401(?![0-9])", re.I),
    "upstream": re.compile(r"(?<![0-9])(?:502|503|504)(?![0-9])|upstream.?error", re.I),
    "timeout": re.compile(r"time.?out|timeout", re.I),
}


def summarize(raw: bytes) -> dict:
    counts = Counter()
    for line in raw.decode("utf-8", "replace").splitlines()[-300:]:
        for category, pattern in INDICATORS.items():
            if pattern.search(line):
                counts[category] += 1
    return {"lines_sampled": min(300, len(raw.splitlines())),
            "indicators": {name: counts[name] for name in INDICATORS},
            "classification": "text_pattern_only_not_request_attribution"}


def collect(command: list[str], *, timeout: int = 14) -> tuple[str, bytes]:
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable", b""
    if result.returncode or len(result.stdout) + len(result.stderr) > MAX_BYTES:
        return "unavailable", b""
    return "available", result.stdout + b"\n" + result.stderr


def workstation(hours: int) -> tuple[str, str, bytes]:
    for name in CONTAINERS_LOCAL:
        state, data = collect(["docker", "logs", "--since", f"{hours}h",
                               "--tail", "300", name])
        if state == "available":
            return state, "docker", data
    state, data = collect(["journalctl", "--user", "-u", "litellm.service",
                           "--since", f"{hours} hours ago", "-n", "300",
                           "-o", "cat", "--no-pager"])
    return state, "user_journal" if state == "available" else "unverified", data


def truenas(hours: int) -> tuple[str, str, bytes]:
    # Strict known-host verification, no agent forwarding, no password prompt.
    # Remote Docker read permission must already be granted; do not attempt sudo.
    command = ["ssh", "-p", PORT, "-T", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no",
               "-o", "ConnectTimeout=5", "-o", "NumberOfPasswordPrompts=0",
               HOST, "docker", "logs", "--since", f"{hours}h",
               "--tail", "300", CONTAINER_TRUENAS]
    state, data = collect(command, timeout=16)
    return state, "ssh_docker" if state == "available" else "unverified", data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--fixture-workstation", type=Path)
    parser.add_argument("--fixture-truenas", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.hours <= 24:
        parser.error("hours must be 1..24")
    if bool(args.fixture_workstation) != bool(args.fixture_truenas):
        parser.error("both fixtures are required together")
    results = {}
    for label, get, fixture in (
        ("workstation", workstation, args.fixture_workstation),
        ("truenas", truenas, args.fixture_truenas),
    ):
        if fixture is not None:
            try:
                if fixture.is_symlink() or fixture.stat().st_size > MAX_BYTES:
                    raise OSError("invalid_fixture")
                data = fixture.read_bytes()
                state, source = "available", "fixture"
            except OSError:
                state, source, data = "unavailable", "unverified", b""
        else:
            state, source, data = get(args.hours)
        entry = {"status": state, "source": source}
        if state == "available":
            entry.update(summarize(data))
        results[label] = entry
    complete = all(item["status"] == "available" for item in results.values())
    print(json.dumps({"read_only": True, "model_requests": 0,
                      "raw_logs_printed": False, "credentials_printed": False,
                      "coverage": "both" if complete else "partial_or_unverified",
                      "sources": results}, sort_keys=True))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
