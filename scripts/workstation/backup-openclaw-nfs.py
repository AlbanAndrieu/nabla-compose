#!/usr/bin/env python3
"""OpenClaw workstation backup to verified NFS mount; no Git or cloud uploads."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

DEFAULT_ROOT = Path("/media/backup/lab/infra/openclaw")
EXPECTED_MOUNT = Path("/media/backup/lab")
EXPECTED_SOURCE = "nabla:/mnt/cpool/backup/lab"
KINDS = ("main", "cron", "global")


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=1800).stdout


def check_mount(root: Path) -> None:
    root = root.absolute()
    if not root.is_relative_to(EXPECTED_MOUNT):
        raise ValueError("backup_root_outside_approved_mount")
    info = json.loads(run("findmnt", "-J", "-T", str(root), "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"))
    fs = info["filesystems"][0]
    if fs["target"] != str(EXPECTED_MOUNT) or fs["source"] != EXPECTED_SOURCE or fs["fstype"] != "nfs4":
        raise ValueError("unexpected_or_missing_nfs_mount")
    if "rw" not in fs["options"].split(","):
        raise ValueError("nfs_mount_not_writable")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_dirs(root: Path) -> None:
    for p in (root, root / "archives", root / "sqlite", root / "sqlite/main",
              root / "sqlite/cron", root / "sqlite/global", root / "sqlite/workboard",
              root / "recovery", root / "manifests"):
        if p.is_symlink():
            raise ValueError("symlink_directory_refused")
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(p, 0o700)


def snapshot_workboard(db: Path, dest: Path) -> Path | None:
    if not db.exists():
        return None
    if db.is_symlink() or not db.is_file():
        raise ValueError("workboard_database_not_regular")
    fd, tmp = tempfile.mkstemp(prefix=".workboard-", suffix=".sqlite", dir=dest)
    os.close(fd)
    target = Path(tmp)
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30) as src:
            with sqlite3.connect(target) as out:
                src.backup(out, pages=128, sleep=0.1)
                if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("workboard_integrity_failed")
        os.chmod(target, 0o600)
        final = dest / ("workboard-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite")
        os.replace(target, final)
        return final
    finally:
        target.unlink(missing_ok=True)


def inventory(root: Path, before: set[str]) -> list[dict]:
    items = []
    for base in (root / "archives", root / "sqlite"):
        for p in base.rglob("*"):
            if p.is_file() and not p.is_symlink() and str(p.relative_to(root)) not in before:
                items.append({"path": str(p.relative_to(root)), "size": p.stat().st_size,
                              "sha256": sha(p)})
    return sorted(items, key=lambda item: item["path"])


def execute(root: Path, workboard: Path, dry_run: bool = False) -> dict:
    check_mount(root)
    if dry_run:
        return {"mount": str(EXPECTED_MOUNT), "source": EXPECTED_SOURCE,
                "destination": str(root), "dry_run": True}
    safe_dirs(root)
    before = {str(p.relative_to(root)) for base in (root / "archives", root / "sqlite")
              for p in base.rglob("*") if p.is_file()}
    for kind in KINDS:
        args = ["openclaw", "backup", "sqlite", "create"]
        args += ["--global"] if kind == "global" else ["--agent", kind]
        run(*(args + ["--repository", str(root / "sqlite" / kind)]))
    workboard_file = snapshot_workboard(workboard, root / "sqlite/workboard")
    run("openclaw", "backup", "create", "--output", str(root / "archives"), "--verify")
    entries = inventory(root, before)
    if not entries or not any(e["path"].startswith("archives/") for e in entries):
        raise ValueError("no_new_archive_detected")
    if len(entries) < 4:
        raise ValueError("missing_expected_sqlite_or_archive_artifacts")
    if workboard_file and not any(e["path"] == str(workboard_file.relative_to(root)) for e in entries):
        raise ValueError("workboard_snapshot_not_detected")
    for e in entries:
        p = root / e["path"]
        if p.stat().st_size != e["size"] or sha(p) != e["sha256"]:
            raise ValueError("backup_verification_failed")
    manifest = {"schema": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "destination": str(root), "mount_source": EXPECTED_SOURCE,
                "workboard_snapshot": workboard_file is not None,
                "files": entries, "verified": True,
                "worm": False, "warning": "SHA-256 manifest is tamper-evident only when independently protected; NFS is not WORM."}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    name = root / "manifests" / ("openclaw-" + stamp + ".json")
    fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    if json.loads(name.read_text())["files"] != entries:
        raise ValueError("manifest_roundtrip_failed")
    return {"manifest": str(name), "files_verified": len(entries),
            "workboard_snapshot": workboard_file is not None,
            "worm": False}


def report(result: dict) -> None:
    """Human-friendly terminal status; machine output stays available via --json."""
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    def paint(value: str, code: str) -> str:
        return f"\\033[{code}m{value}\\033[0m" if color else value
    print(paint("🔐 OpenClaw · NFS backup", "1;36"))
    if result.get("dry_run"):
        print(paint("✅ Montage NFS vérifié", "32"))
        print(f"📂 Destination : {result['destination']}")
        print(f"🔗 Source      : {result['source']}")
        print("ℹ️  Simulation : aucune sauvegarde créée")
    else:
        print(paint("✅ Sauvegarde et empreintes vérifiées", "32"))
        print(f"📦 Fichiers contrôlés : {result['files_verified']}")
        print(f"🗃️  Workboard SQLite : {'snapshot vérifié' if result['workboard_snapshot'] else 'absent (non sauvegardé)'}")
        print(f"🧾 Manifest : {result['manifest']}")
        print(paint("⚠️  Manifest non WORM ; stockage/chiffrement à contrôler", "33"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workboard", type=Path,
                        default=Path.home() / ".openclaw/plugins/workboard/workboard.sqlite")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON only")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = execute(args.root, args.workboard, args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            report(result)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, sqlite3.Error) as exc:
        raise SystemExit(f"❌ ERREUR : sauvegarde non confirmée ({type(exc).__name__})") from None


if __name__ == "__main__":
    main()
