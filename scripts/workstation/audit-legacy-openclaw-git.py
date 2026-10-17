#!/usr/bin/env python3
"""Read-only inventory of historical OpenClaw Git dotfiles before migration."""
from __future__ import annotations

import argparse
import json
import subprocess

SENSITIVE = {".env", "gateway.systemd.env", "openclaw.json",
             "exec-approvals.json"}


def inventory(repo: str, prefix: str) -> dict:
    result = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", "HEAD", "--", prefix],
        check=True, capture_output=True, text=True, timeout=15,
    )
    rows = []
    for path in result.stdout.splitlines():
        name = path.rsplit("/", 1)[-1]
        rows.append({"path": path, "classification":
                     "sensitive_review_required" if name in SENSITIVE
                     or "/agents/" in path or "/skills/" in path
                     else "review_before_migration"})
    return {"files": rows, "cleanup_performed": False,
            "note": "Inventory only; Git history and tracked secrets are untouched."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Local checkout of nabla")
    parser.add_argument("--prefix", default="env/home/dotfiles/.openclaw")
    args = parser.parse_args()
    print(json.dumps(inventory(args.repo, args.prefix), indent=2))


if __name__ == "__main__":
    main()
