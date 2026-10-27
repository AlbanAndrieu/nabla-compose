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
SKILL_TEMPLATE = (Path.home() / ".openclaw/workspace/skills/tech-news-digest/"
                  "references/digest-prompt.md")
MAX_JSON = 1024 * 1024
TOP_PATTERN = re.compile(r'(?<!\S)--top(?:\s+|=)(?:["\']?)([^\s"\']+)')
INVALID_RANGE = re.compile(r"^\d+[-\u2013\u2014]\d+$")
INTEGER = re.compile(r"^[0-9]+$")
ITEMS_PARAMETER = re.compile(r"(?m)^\s*-\s*ITEMS_PER_SECTION\s*=\s*([^\s]+)")
FIXED_TOP = re.compile(r"(?<!\S)--top\s+([0-9]+)(?![0-9])")
# Detect the specific natural-language range which caused the 27 Oct failure.
# Do not try to interpret arbitrary dates, version numbers or prompt contents.
NATURAL_TOP_RANGE = re.compile(r"(?<![0-9])3\s*[-\u2013\u2014]\s*5(?![0-9])")


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


def classify_job(job: dict | None, skill_template: str | None = None) -> tuple[str, str]:
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
    # When the cron references a skill, inspect the authoritative template.
    # An explanatory '--top 5' appended to cron cannot override its script.
    if "references/digest-prompt.md" in message:
        params = ITEMS_PARAMETER.findall(message)
        if len(params) != 1:
            return "skill_items_parameter_unverified", "5"
        items = params[0]
        if skill_template is None:
            return "skill_template_unavailable", "5"
        if "--top <ITEMS_PER_SECTION>" in skill_template:
            return ("skill_template_integer_valid" if INTEGER.fullmatch(items)
                    else "skill_template_range_int_mismatch"), "5"
        if FIXED_TOP.search(skill_template):
            return "skill_template_fixed_integer", "5"
        return "skill_template_top_unverified", "5"
    values = TOP_PATTERN.findall(message)
    if not values:
        return ("natural_language_top_range" if NATURAL_TOP_RANGE.search(message)
                else "no_explicit_top_argument"), "5"
    if len(set(values)) != 1:
        return "multiple_top_arguments", "5"
    value = values[0]
    if INVALID_RANGE.fullmatch(value):
        return "invalid_top_range", "5"
    if INTEGER.fullmatch(value):
        if int(value) != 5:
            return "valid_other_integer", "5"
        # Mixing an explicit --top 5 with a 3-5 range is ambiguous to an agent.
        if NATURAL_TOP_RANGE.search(message):
            return "ambiguous_mixed_top_guidance", "5"
        return "valid_top_five", "5"
    return "invalid_top_value", "5"


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


def read_skill_template(path: Path = SKILL_TEMPLATE) -> tuple[str, str | None]:
    """Read only an owner-controlled regular Markdown file, never print content."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022 or info.st_size > MAX_JSON
                    or info.st_nlink != 1):
                return "unsafe_file", None
            raw = os.read(fd, MAX_JSON + 1)
        finally:
            os.close(fd)
        if not raw or len(raw) > MAX_JSON:
            return "invalid_file", None
        return "available", raw.decode("utf-8")
    except (OSError, UnicodeError):
        return "unavailable", None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Offline private job JSON fixture")
    args = parser.parse_args(argv)
    state, job = read_fixture(args.fixture) if args.fixture else read_runtime()
    template_state, template = read_skill_template()
    classification, recommendation = classify_job(job, template)
    print("openclaw_digest_audit=read_only")
    print("cron_job_read=" + state)
    print("skill_template_read=" + template_state)
    print("digest_top_argument=" + classification)
    print("recommended_integer_top=" + recommendation)
    print("cron_job_modified=false")
    print("model_requests_sent=0")
    print("task_prompt_printed=false")
    # Passing contracts is not proof a model will follow its prompt or a job will deliver.
    valid = ("valid_top_five", "skill_template_integer_valid",
             "skill_template_fixed_integer")
    return 0 if state == "structured" and classification in valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
