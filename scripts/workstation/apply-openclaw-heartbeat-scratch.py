#!/usr/bin/env python3
"""Safely stage a sanitized OpenClaw heartbeat scratch; never run the heartbeat."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

JOB = "bb9757db-9559-4960-bb23-9b9770929ff1"
TEMPLATE = Path(__file__).resolve().parents[2] / "apps/openclaw/workstation/HEARTBEAT-SCRATCH.template.md"
BACKUP = Path("/media/backup/lab/infra/openclaw/recovery/heartbeat-scratch-before.txt")
MOUNT = "/media/backup/lab"
SOURCE = "nabla:/mnt/cpool/backup/lab"
EXPECTED_SHA = "5b6aff82b20e1f59e8c0c6dc2cc2b52b1cf7163c8c493b8dfa137d1e77189cc4"

def call(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=45).stdout

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Replace native scratch with reviewed generic template")
    args = p.parse_args()
    os.umask(0o077)
    mount = call("findmnt", "-T", str(BACKUP), "-no", "TARGET,SOURCE,FSTYPE").strip().split()
    if mount != [MOUNT, SOURCE, "nfs4"]:
        raise SystemExit("❌ Unexpected NFS mount; refusing")
    if not BACKUP.is_file() or BACKUP.is_symlink():
        raise SystemExit("❌ Original scratch backup missing")
    if hashlib.sha256(BACKUP.read_bytes()).hexdigest() != EXPECTED_SHA:
        raise SystemExit("❌ Original scratch backup checksum mismatch")
    current = json.loads(call("openclaw", "cron", "scratch", JOB, "--json"))
    revision = current["currentRevision"]
    existing = current["scratch"]["content"]
    desired = TEMPLATE.read_text(encoding="utf-8")
    if existing == desired:
        print("✅ Scratch already matches sanitized template")
        return
    print(f"🔐 Original scratch verified on NFS; native revision={revision}")
    if not args.apply:
        print("ℹ️  Dry-run only. Use --apply after review to replace scratch without running agent.")
        return
    if revision != 1:
        raise SystemExit("❌ Unexpected scratch revision; manual review required")
    result = call("openclaw", "cron", "scratch", JOB, "--file", str(TEMPLATE), "--expected-revision", str(revision), "--json")
    after = json.loads(call("openclaw", "cron", "scratch", JOB, "--json"))
    if after["scratch"]["content"] != desired:
        raise SystemExit("❌ Scratch write not confirmed")
    print("✅ Sanitized heartbeat scratch applied and read back; no heartbeat execution requested")
    print("⚠️  Observe subsequent native cron status; no claim of runner recovery")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        raise SystemExit(f"❌ Heartbeat scratch operation failed ({type(e).__name__})") from None
