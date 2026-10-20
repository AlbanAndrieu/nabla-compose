#!/usr/bin/env python3
"""Offline, value-blind readiness audit. Never accesses TrueNAS, secrets or a network."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPECTED_IDS = {
    "secrets-runtime",
    "defectdojo",
    "backstage-v2",
    "openclaw-litellm",
    "openrag-docling-bababou",
    "observability",
    "freshrss-gitops-mcp",
}
PHASES = {
    "planned",
    "repository_ready",
    "runtime_observed",
    "runtime_accepted",
    "reboot_accepted",
}
VERIFIED = {"runtime_accepted", "reboot_accepted"}
REQUIRED_FIELDS = {"id", "priority", "phase", "requires", "artifacts", "acceptance"}


def validate(manifest: object, root: Path) -> list[str]:
    """Validate declarative dependencies and local files, not runtime health."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest: expected an object"]
    if manifest.get("schemaVersion") != 1 or manifest.get("scope") != "repository-evidence-only":
        errors.append("manifest: unsupported schema or runtime evidence scope")
    if manifest.get("runtimeAcceptance") is not False:
        errors.append("manifest: runtimeAcceptance must remain false without live evidence")
    items = manifest.get("workstreams")
    if not isinstance(items, list):
        return errors + ["manifest: workstreams must be an array"]
    ids: set[str] = set()
    deps: dict[str, list[str]] = {}
    for index, item in enumerate(items):
        label = f"workstreams[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: expected object")
            continue
        if set(item) != REQUIRED_FIELDS:
            errors.append(f"{label}: required fields only (no credential/evidence payloads)")
            continue
        ident = item["id"]
        if not isinstance(ident, str) or ident not in EXPECTED_IDS or ident in ids:
            errors.append(f"{label}: missing, unknown or duplicate identifier")
            continue
        ids.add(ident)
        phase = item["phase"]
        if not isinstance(phase, str) or phase not in PHASES or phase in VERIFIED:
            errors.append(f"{ident}: live acceptance cannot be asserted by this offline manifest")
        if not isinstance(item["priority"], str) or item["priority"] not in {"P0", "P1", "P2", "P3"}:
            errors.append(f"{ident}: invalid priority")
        requires = item["requires"]
        if not isinstance(requires, list) or any(not isinstance(x, str) for x in requires):
            errors.append(f"{ident}: requires must contain identifiers")
            requires = []
        if any(not isinstance(dep, str) for dep in requires) or len(requires) != len(set(dep for dep in requires if isinstance(dep, str))):
            errors.append(f"{ident}: duplicate dependency")
        deps[ident] = requires
        artifacts = item["artifacts"]
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"{ident}: at least one existing repository artifact required")
        else:
            for name in artifacts:
                if not isinstance(name, str) or not name or Path(name).is_absolute():
                    errors.append(f"{ident}: invalid repository artifact path")
                    continue
                path = (root / name).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    errors.append(f"{ident}: absent or unsafe artifact {name}")
        acceptance = item["acceptance"]
        if not isinstance(acceptance, list) or len(acceptance) < 2 or any(
            not isinstance(x, str) or not x.strip() for x in acceptance
        ):
            errors.append(f"{ident}: need at least two explicit acceptance criteria")
    if ids != EXPECTED_IDS:
        errors.append("manifest: missing workstreams")
    for ident, prereqs in deps.items():
        if ident in prereqs or any(dep not in ids for dep in prereqs):
            errors.append(f"{ident}: invalid dependency")
    visited: set[str] = set()
    active: set[str] = set()

    def visit(ident: str) -> None:
        if ident in active:
            errors.append(f"{ident}: dependency cycle")
            return
        if ident in visited:
            return
        active.add(ident)
        for dep in deps.get(ident, []):
            if dep in deps:
                visit(dep)
        active.remove(ident)
        visited.add(ident)

    for ident in sorted(deps):
        visit(ident)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = (args.manifest or root / "config/migrations/workstreams.json").resolve()
    if not manifest_path.is_relative_to(root):
        print("manifest: path outside repository", file=sys.stderr)
        return 2
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("manifest: unreadable or invalid JSON", file=sys.stderr)
        return 2
    errors = validate(data, root)
    phases = {
        item["id"]: item["phase"]
        for item in data.get("workstreams", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
        and isinstance(item.get("phase"), str)
    } if isinstance(data, dict) else {}
    if args.json:
        print(json.dumps({"result": "FAIL" if errors else "PASS", "scope": "offline-only",
                          "runtimeAccepted": False, "phases": phases, "errors": errors},
                         sort_keys=True))
    else:
        print(f"{'FAIL' if errors else 'PASS'}: offline migration contract; "
              f"runtime acceptance NOT VERIFIED ({len(phases)} workstreams)")
        for error in errors:
            print(f"  - {error}")
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
