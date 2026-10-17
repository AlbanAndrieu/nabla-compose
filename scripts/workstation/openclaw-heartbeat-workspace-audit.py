#!/usr/bin/env python3
"""Read-only OpenClaw heartbeat workspace audit. Never print file contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def inspect(root: Path) -> dict:
    paths = {
        "main_workspace": root / "workspace/HEARTBEAT.md",
        "cron_workspace": root / "workspace/cron/HEARTBEAT.md",
    }
    rows = []
    for name, path in paths.items():
        if path.is_symlink():
            rows.append({"role": name, "status": "symlink_refused"})
            continue
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            rows.append({"role": name, "status": "absent"})
            continue
        except (OSError, PermissionError):
            rows.append({"role": name, "status": "unreadable"})
            continue
        rows.append({
            "role": name,
            "status": "present",
            "bytes": len(data),
            "lines": len(data.splitlines()),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    sandbox = root / "sandboxes"
    rows.append({
        "role": "sandbox_heartbeat_files",
        "count": sum(1 for p in sandbox.glob("agent-*/HEARTBEAT.md") if p.is_file() and not p.is_symlink())
        if sandbox.is_dir() else 0,
        "status": "inventory_only_not_active_proof",
    })
    return {"files": rows, "active_workspace": "not_determined",
            "note": "No prompt contents, secrets, session data, or network calls. "
                    "Presence/hash cannot prove which file the gateway loads."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".openclaw")
    args = parser.parse_args()
    print(json.dumps(inspect(args.root), indent=2))


if __name__ == "__main__":
    main()
