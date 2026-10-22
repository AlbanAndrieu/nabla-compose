#!/usr/bin/env python3
"""Offline pre-commit manifest integrity check (no hook installation or network)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".pre-commit-config.yaml"


def validate(config: object) -> list[str]:
    """Find duplicate hooks and repeated external hook repositories."""
    if not isinstance(config, dict) or not isinstance(config.get("repos"), list):
        return ["pre-commit config must contain a repos list"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    external: set[tuple[str, str]] = set()
    for index, item in enumerate(config["repos"], 1):
        if not isinstance(item, dict):
            errors.append(f"repo #{index} is not a mapping")
            continue
        repo = item.get("repo")
        rev = item.get("rev")
        if not isinstance(repo, str) or not repo:
            errors.append(f"repo #{index} has no valid source")
            continue
        if repo != "local":
            if not isinstance(rev, str) or not rev:
                errors.append(f"{repo}: missing revision pin")
            else:
                key = (repo, rev)
                if key in external:
                    errors.append(f"duplicate repository: {repo}@{rev}")
                external.add(key)
        hooks = item.get("hooks")
        if not isinstance(hooks, list):
            errors.append(f"{repo}: hooks must be a list")
            continue
        for hook in hooks:
            hook_id = hook.get("id") if isinstance(hook, dict) else None
            if not isinstance(hook_id, str) or not hook_id:
                errors.append(f"{repo}: invalid hook id")
            elif hook_id in seen_ids:
                errors.append(f"duplicate hook id: {hook_id}")
            else:
                seen_ids.add(hook_id)
    return errors


def main() -> int:
    try:
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"pre-commit manifest invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    errors = validate(config)
    for error in errors:
        print(f"pre-commit manifest invalid: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"pre-commit manifest OK: {len(config['repos'])} repositories, "
          f"{sum(len(x['hooks']) for x in config['repos'])} distinct hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
