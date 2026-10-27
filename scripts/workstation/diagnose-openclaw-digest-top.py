#!/usr/bin/env python3
"""Read-only, redacted audit of the daily tech digest OpenClaw cron argument.

Never prints task prompts, secrets, URLs, recipients or raw CLI output.
No cron edit, model request, job execution, service restart or quota change.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess

JOB_ID = "7ed5dd9a-da30-479f-b0eb-4cc494fb4966"
JOB_NAME = "daily-tech-news-digest"
NODE_ROOT = Path.home() / ".local/share/mise/installs/node/24.22.1"
NODE = NODE_ROOT / "bin/node"
CLI = NODE_ROOT / "lib/node_modules/openclaw/openclaw.mjs"
MAX_JSON = 1024 * 1024
TOP_PATTERN = re.compile(r'(?<!\S)--top(?:\s+|=)(?:["\']?)([^\s"\']+)')
INVALID_RANGE = re.compile(r"^\d+[-\u2013\u2014]\d+$")
INTEGER = re.compile(r"^[0-9]+$")


def owned_file(path: Path) -> bool:
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022 and info.st_nlink == 1)
    except OSError:
        return False


def decode_job(raw: bytes) -> dict | None:
    if not raw or len(raw) > MAX_JSON:
        return None
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    job = value.get("job", value)
    return job if isinstance(job, dict) else None


def classify_job(job: dict | None) -> tuple[str, str]:
    if job is None:
        return "unavailable", "unverified"
    if job.get("id") != JOB_ID or job.get("name") != JOB_NAME:
        return "wrong_job", "unverified"
    payload = job.get("payload")
    if not isinstance(payload, dict):
        return "unexpected_payload", "unverified"
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        return "unexpected_payload", "unverified"
    values = TOP_PATTERN.findall(message)
    if not values:
        return "no_explicit_top_argument", "unverified"
    if len(values) != 1:
        return "multiple_top_arguments", "unverified"
    value = values[0]
    if INVALID_RANGE.fullmatch(value):
        return "invalid_top_range", "five"
    if INTEGER.fullmatch(value):
        return ("valid_top_five" if int(value) == 5 else "valid_other_integer",
                "five")
    return "invalid_top_value", "five"


def read_runtime(node: Path = NODE, cli: Path = CLI) -> tuple[str, dict | None]:
    if not owned_file(node) or not owned_file(cli):
        return "unverified_installation", None
    try:
        result = subprocess.run(
            [str(node), str(cli), "cron", "get", JOB_ID],
            capture_output=True, check=False, timeout=25,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "cli_unavailable", None
    if result.returncode:
        return "cli_failed", None
    job = decode_job(result.stdout)
    return ("structured" if job is not None else "invalid_report"), job


def read_fixture(path: Path) -> tuple[str, dict | None]:
    if not owned_file(path):
        return "unsafe_fixture", None
    try:
        if path.stat().st_size > MAX_JSON:
            return "invalid_report", None
        job = decode_job(path.read_bytes())
    except OSError:
        return "invalid_report", None
    return ("structured" if job is not None else "invalid_report"), job


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline private job JSON fixture")
    args = parser.parse_args(argv)
    state, job = read_fixture(args.fixture) if args.fixture else read_runtime()
    classification, recommendation = classify_job(job)
    print("openclaw_digest_audit=read_only")
    print("cron_job_read=" + state)
    print("digest_top_argument=" + classification)
    print("recommended_integer_top=" + recommendation)
    print("cron_job_modified=false")
    print("model_requests_sent=0")
    print("task_prompt_printed=false")
    return 0 if state == "structured" and classification in (
        "valid_top_five", "valid_other_integer") else 2


if __name__ == "__main__":
    raise SystemExit(main())
