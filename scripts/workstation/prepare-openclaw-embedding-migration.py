#!/usr/bin/env python3
"""OpenClaw embedding migration preflight and guarded backup (no config mutation)."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

KEY = Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key"
BASE = Path.home() / ".openclaw"
BACKUP = Path.home() / ".local/share/nabla-compose/openclaw-memory-migration"

def decorate(line):
    """Human-friendly TTY output; plain stable key=value for CI and pipes."""
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ or os.getenv("TERM") == "dumb":
        return line
    if line.startswith("runtime_") and line.endswith("=verified"):
        return "\033[32m✔ " + line + "\033[0m"
    if line.startswith("runtime_") and line.endswith("=unresolved"):
        return "\033[31m✘ " + line + "\033[0m"
    if line.startswith("WARN:"):
        return "\033[33m⚠ " + line + "\033[0m"
    if line.startswith("ERROR:"):
        return "\033[31m✘ " + line + "\033[0m"
    if line.startswith("NOTE:"):
        return "\033[36mℹ " + line + "\033[0m"
    if line.startswith(("migration_stage=", "active_databases_verified=", "sqlite_backups_verified=")):
        return "\033[1;34m◆ " + line + "\033[0m"
    if line in ("virtual_key_file=private", "memory_search_schema=compatible"):
        return "\033[32m✔ " + line + "\033[0m"
    return line

def report(line):
    print(decorate(line))

def cli(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None

def active_databases():
    """Use runtime-declared dbPath for both agents, without exposing paths."""
    data = cli("openclaw", "memory", "status", "--json")
    if not isinstance(data, list):
        return {}
    result = {}
    for record in data:
        if not isinstance(record, dict):
            continue
        agent = record.get("agentId")
        status = record.get("status")
        if agent not in ("main", "cron") or not isinstance(status, dict):
            continue
        name = status.get("dbPath")
        expected = status.get("storage", {}).get("databaseBytes")
        if not isinstance(name, str) or not Path(name).is_absolute():
            continue
        p = Path(name)
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size != expected:
                continue
            with p.open("rb") as handle:
                if handle.read(16) != b"SQLite format 3\x00":
                    continue
            result[agent] = p
        except OSError:
            continue
    return result

def verify_backups():
    """Verify an existing private snapshot without reading or changing active indexes."""
    if BACKUP.is_symlink() or not BACKUP.is_dir() or BACKUP.stat().st_mode & 0o077:
        report("ERROR: private backup directory missing or insecure")
        return 2
    snapshots = sorted((p for p in BACKUP.iterdir() if p.is_dir() and not p.is_symlink()), reverse=True)
    if not snapshots:
        report("ERROR: no backup snapshot available")
        return 2
    for snapshot in snapshots:
        if snapshot.stat().st_mode & 0o077:
            continue
        valid = True
        for agent in ("main", "cron"):
            path = snapshot / (agent + ".sqlite")
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                valid = False
                break
            try:
                connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=5)
                try:
                    valid = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                finally:
                    connection.close()
            except (OSError, sqlite3.Error):
                valid = False
            if not valid:
                break
        if valid:
            report("backup_snapshot=verified")
            report("sqlite_backups_verified=2")
            report("migration_applied=false")
            return 0
    report("ERROR: no complete, private, integrity-checked backup snapshot found")
    return 2

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--verify-backup", action="store_true", help="Read-only integrity verification of existing private SQLite snapshots")
    modes.add_argument("--apply", action="store_true", help="Back up discovered SQLite indexes only; does NOT migrate")
    args = parser.parse_args()
    if args.verify_backup:
        report("migration_stage=verify_backup")
        return verify_backups()
    report("migration_stage=preflight" if args.check else "migration_stage=backup_only")
    key_ok = KEY.is_file() and not KEY.is_symlink() and KEY.stat().st_mode & 0o077 == 0
    report("virtual_key_file=" + ("private" if key_ok else "missing_or_insecure"))
    schema = cli("openclaw", "config", "schema", "--json")
    props = (schema or {}).get("properties", {}).get("memory", {}).get("properties", {}).get("search", {}).get("properties", {})
    schema_ok = all(k in props for k in ("provider", "model", "remote"))
    report("memory_search_schema=" + ("compatible" if schema_ok else "unresolved"))
    indexes = active_databases()
    for agent in ("main", "cron"):
        report(f"runtime_{agent}_database=" + ("verified" if agent in indexes else "unresolved"))
    report(f"active_databases_verified={len(indexes)}")
    report("expected_existing_dimensions=768")
    report("target_model=embedding backend=ollama/nomic-embed-text")
    report("NOTE: matching dimensions do not imply matching vector spaces")
    if args.check:
        report("NOTE: read-only; no embeddings call, configuration change or reindex")
        return 0 if key_ok and schema_ok and len(indexes) == 2 else 2
    if not key_ok or not schema_ok or len(indexes) != 2:
        print("ERROR: active index paths unresolved or migration artifact found; backup not started", file=sys.stderr)
        return 2
    if BACKUP.is_symlink():
        print("ERROR: backup root is symlink", file=sys.stderr)
        return 2
    BACKUP.mkdir(parents=True, mode=0o700, exist_ok=True)
    if BACKUP.stat().st_mode & 0o077:
        print("ERROR: backup directory permissions too broad", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP / stamp
    dest.mkdir(mode=0o700)
    for agent in ("main", "cron"):
        source = indexes[agent]
        target = dest / (agent + ".sqlite")
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=5)
            target_conn = sqlite3.connect(str(target))
            try:
                source_conn.backup(target_conn)
                if target_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("integrity_check failed")
            finally:
                target_conn.close()
                source_conn.close()
            target.chmod(0o600)
        except (OSError, sqlite3.Error, RuntimeError):
            print("ERROR: SQLite backup failed; inspect private backup directory", file=sys.stderr)
            return 1
    report(f"sqlite_backups_verified={len(indexes)}")
    report("migration_applied=false")
    report("NOTE: no configuration changes, provider requests or reindex performed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
