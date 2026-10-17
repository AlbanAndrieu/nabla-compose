#!/usr/bin/env python3
"""Backup OpenClaw workspace Markdown without following symlinks or printing content."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

ROOT = Path.home() / ".local/share/nabla-compose/openclaw-memory-migration"
OPENCLAW = Path.home() / ".openclaw"


def workspaces():
    command = subprocess.run(
        ["openclaw", "memory", "status", "--json"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if command.returncode:
        raise RuntimeError("OpenClaw memory status unavailable")
    records = json.loads(command.stdout)
    if not isinstance(records, list):
        raise RuntimeError("Unexpected OpenClaw memory status format")
    paths = {}
    for record in records:
        if not isinstance(record, dict) or record.get("agentId") not in ("main", "cron"):
            continue
        workspace = record.get("status", {}).get("workspaceDir")
        if isinstance(workspace, str) and Path(workspace).is_absolute():
            paths[record["agentId"]] = Path(workspace)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("choose exactly one of --check or --apply")
    try:
        paths = workspaces()
        if set(paths) != {"main", "cron"}:
            raise RuntimeError("Workspace paths missing; refusing guessed paths")
        files = []
        for agent, workspace in sorted(paths.items()):
            if workspace.is_symlink() or not workspace.is_dir():
                raise RuntimeError("Workspace missing or symlink")
            for base, dirs, names in os.walk(workspace, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
                for name in names:
                    source = Path(base) / name
                    if source.suffix.lower() != ".md" or source.is_symlink():
                        continue
                    metadata = source.lstat()
                    if not stat.S_ISREG(metadata.st_mode):
                        continue
                    relative = source.relative_to(workspace)
                    files.append((agent, workspace, relative, source))
        print(f"workspaces_verified={len(paths)} markdown_files={len(files)}")
        if args.check:
            print("backup_created=false")
            return 0
        if ROOT.is_symlink():
            raise RuntimeError("Backup root is a symlink")
        ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
        if ROOT.stat().st_mode & 0o077:
            raise RuntimeError("Backup root permissions are too broad")
        destination = ROOT / ("markdown-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        destination.mkdir(mode=0o700)
        archive = destination / "memory-markdown.tar.gz"
        manifest = []
        with tarfile.open(archive, "w:gz", dereference=False) as tar:
            for agent, workspace, relative, source in files:
                if source.is_symlink() or not source.is_file():
                    raise RuntimeError("Source changed during backup")
                data = source.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                name = f"{agent}/{relative.as_posix()}"
                import io
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o600
                tar.addfile(entry, io.BytesIO(data))
                manifest.append({"path": name, "size": len(data), "sha256": digest})
        archive.chmod(0o600)
        manifest_file = destination / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifest_file.chmod(0o600)
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            if len(members) != len(manifest):
                raise RuntimeError("Archive member count mismatch")
            for member, expected in zip(members, manifest):
                if member.name != expected["path"] or not member.isfile():
                    raise RuntimeError("Unexpected archive member")
                stream = tar.extractfile(member)
                if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected["sha256"]:
                    raise RuntimeError("Archive checksum mismatch")
        print(f"backup_verified=true markdown_files={len(manifest)}")
        print("source_files_modified=false")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, tarfile.TarError) as error:
        print("ERROR: Markdown backup failed; no source files were intentionally modified", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
