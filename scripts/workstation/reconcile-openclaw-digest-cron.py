#!/usr/bin/env python3
"""Declarative digest cron reconciliation; no new jobs, secrets or inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/openclaw/workstation/cron/daily-tech-news-digest.message.md"
JOB_ID = "7ed5dd9a-da30-479f-b0eb-4cc494fb4966"
JOB_NAME = "daily-tech-news-digest"
MAX_BYTES = 1024 * 1024


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def desired_message(path=SOURCE):
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or path.is_symlink()
            or meta.st_size > 16 * 1024 or meta.st_size == 0):
        raise ValueError("unsafe_source")
    message = path.read_text(encoding="utf-8").strip()
    if (message.count("- ITEMS_PER_SECTION = 5") != 1
            or "references/digest-prompt.md" not in message
            or re.search(r"(?i)(?:sk-[a-z0-9]{12,}|api[_-]?key\s*=|token\s*=)", message)):
        raise ValueError("invalid_versioned_message")
    return message


def runtime_job():
    mod = module("nabla_digest_audit", "diagnose-openclaw-digest-top.py")
    state, job = mod.read_runtime()
    if (state != "structured" or not isinstance(job, dict)
            or job.get("id") != JOB_ID or job.get("name") != JOB_NAME):
        return None
    payload = job.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
        return None
    if payload.get("kind") not in ("agentTurn", None):
        return None
    return job


def host():
    return module("nabla_host", "openclaw-host-context.py").detect()


def cli_edit(message):
    paths = module("nabla_paths", "openclaw_runtime_paths.py")
    node, entry = paths.pinned_cli_paths()
    if not node.is_file() or not entry.is_file():
        return False
    # Only a versioned, public, secret-free message goes into process argv.
    # Never put an existing private job prompt on a command line.
    try:
        result = subprocess.run(
            [str(node), str(entry), "automations", "edit", JOB_ID,
             "--message", message],
            stdin=subprocess.DEVNULL, capture_output=True,
            timeout=35, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def backup(job):
    target = Path.home() / ".local/state/nabla-compose/openclaw/digest-gitops"
    # Existing unsafe parents are not re-permissioned.
    for parent in (Path.home() / ".local", Path.home() / ".local/state",
                   Path.home() / ".local/state/nabla-compose",
                   Path.home() / ".local/state/nabla-compose/openclaw", target):
        if parent.is_symlink():
            raise ValueError("unsafe_parent_symlink")
        if not parent.exists():
            parent.mkdir(mode=0o700)
        m = parent.stat()
        if m.st_uid != os.geteuid() or m.st_mode & 0o022:
            raise ValueError("unsafe_parent_permissions")
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = target / ("digest-before-" + now + ".json")
    raw = json.dumps(job, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("snapshot_too_large")
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return True


def preserved(old, new):
    return all(old.get(field) == new.get(field) for field in (
        "schedule", "delivery", "agentId", "sessionTarget", "enabled"
    )) and {
        k: v for k, v in old["payload"].items() if k != "message"
    } == {
        k: v for k, v in new["payload"].items() if k != "message"
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--plan", action="store_true")
    options.add_argument("--check", action="store_true")
    options.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-message-sha", default="")
    args = parser.parse_args(argv)

    if host() != "workstation":
        print("⚠️  WRONG_HOST: cron GitOps applies only to OpenClaw Workstation")
        print("cron_gitops=not_applicable_or_unverified")
        return 2
    try:
        desired = desired_message()
    except (OSError, ValueError, UnicodeError):
        print("cron_gitops=invalid_source")
        return 2
    job = runtime_job()
    if job is None:
        print("cron_gitops=runtime_job_unverified")
        return 2
    before = job["payload"]["message"]
    old_sha = sha(before)
    new_sha = sha(desired)
    print("cron_gitops=existing_job_only")
    print("job_identity=verified")
    print("runtime_message_sha256=" + old_sha)
    print("desired_message_sha256=" + new_sha)
    print("job_schedule_and_delivery=preserved_by_design")
    print("model_requests=0")
    if before == desired:
        print("cron_gitops=already_aligned")
        return 0
    print("cron_gitops=drift")
    if not args.apply:
        return 2 if args.check else 0
    if not re.fullmatch("[0-9a-f]{64}", args.expected_message_sha):
        print("apply=blocked_missing_expected_digest")
        return 2
    if old_sha != args.expected_message_sha:
        print("apply=blocked_concurrent_drift")
        return 2
    # Only migrate the known affected skill contract. A different private
    # message may contain custom instructions; do not overwrite it blindly.
    if (before.count("ITEMS_PER_SECTION = 3-5") != 1
            or "references/digest-prompt.md" not in before):
        print("apply=blocked_unexpected_runtime_template_review_in_ui")
        return 2
    state = job.get("state")
    if isinstance(state, dict) and state.get("runningAtMs"):
        print("apply=blocked_running_job")
        return 2
    current = runtime_job()
    if current is None or sha(current["payload"]["message"]) != old_sha:
        print("apply=blocked_concurrent_drift")
        return 2
    try:
        backup(job)
    except (OSError, ValueError):
        print("apply=blocked_private_backup")
        return 2
    print("private_backup=created_0600")
    if not cli_edit(desired):
        print("apply=cli_failed_no_runtime_proof")
        return 2
    after = runtime_job()
    if (after is None or after["payload"]["message"] != desired
            or not preserved(job, after)):
        print("apply=unverified_after_edit_review_snapshot_privately")
        return 2
    print("apply=verified_existing_job_updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
