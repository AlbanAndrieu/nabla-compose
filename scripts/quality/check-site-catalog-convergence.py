#!/usr/bin/env python3
"""Read-only Backstage v2 and icon-contract audit for Nabla's shared catalog.

Optional --site-generated validates the website's local generated icon map.
No HTTP, runtime probing, secret access, code generation or deployment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
REVISION = re.compile(r"sha256:[a-f0-9]{64}\Z")
REFERENCE = re.compile(r"(api|component|resource):[a-z0-9-]+/[a-z0-9-]+\Z")
ICON_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ICON_FILE = re.compile(r"[a-zA-Z0-9._-]+\.(?:svg|png|jpg)\Z")
TS_EXPORT = "export const HOMELAB_CATALOG_ICON_FILES: Readonly<Record<string, string>> = "


def icon_for(name: str, mapping: dict[str, str]) -> str | None:
    """Mirror the site's exact-ID/longest-parent icon lookup semantics."""
    if name in mapping:
        return mapping[name]
    parents = (parent for parent in mapping if name.startswith(parent + "-"))
    closest = max(parents, key=len, default=None)
    return mapping[closest] if closest else None


def audit(root: Path, site_generated: Path | None = None) -> tuple[list[str], dict[str, int]]:
    """Validate source identity and optional derived site asset mapping."""
    errors: list[str] = []
    stats: dict[str, int] = {}
    try:
        canonical = json.loads((root / "catalog/generated/entities.json").read_text(encoding="utf-8"))
        catalog = json.loads((root / "catalog/service-icons.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"unreadable or invalid catalog source: {type(exc).__name__}"], stats
    if not isinstance(canonical, dict) or canonical.get("schemaVersion") != 2 or canonical.get("model") != "backstage":
        return ["expected Backstage v2 catalog"], stats
    entities = canonical.get("entities")
    revision = canonical.get("catalogRevision")
    if not isinstance(entities, list) or not entities or not all(isinstance(e, dict) for e in entities):
        return ["missing or malformed Backstage entities"], stats
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        errors.append("invalid catalogRevision format")
    else:
        ordered = sorted(entities, key=lambda entity: str(entity.get("entityRef") or ""))
        serialized = json.dumps(ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        expected = "sha256:" + hashlib.sha256(serialized).hexdigest()
        if expected != revision:
            errors.append("catalogRevision does not match the canonical Backstage graph")
    if not isinstance(catalog, dict) or catalog.get("version") != 1 or not isinstance(catalog.get("webAssets"), dict):
        return errors + ["invalid webAssets mapping"], stats
    mapping = catalog["webAssets"]
    for key, value in mapping.items():
        if not isinstance(key, str) or not ICON_ID.fullmatch(key):
            errors.append("unsafe service icon ID")
            break
        if not isinstance(value, str) or not ICON_FILE.fullmatch(value) or ".." in value:
            errors.append("unsafe icon asset filename")
            break
    identities: set[str] = set()
    names: list[str] = []
    missing_icons = 0
    for item in entities:
        kind = item.get("kind")
        if kind not in ("Component", "Resource", "API"):
            continue
        ref = item.get("entityRef")
        meta = item.get("metadata")
        if not isinstance(ref, str) or not REFERENCE.fullmatch(ref) or ref in identities:
            errors.append("invalid or duplicate canonical service entityRef")
            continue
        identities.add(ref)
        if not isinstance(meta, dict) or not isinstance(meta.get("name"), str):
            errors.append("missing canonical metadata.name")
            continue
        name = meta["name"]
        namespace = meta.get("namespace", "default")
        if not isinstance(namespace, str) or ref != f"{kind.lower()}:{namespace}/{name}":
            errors.append("inconsistent Backstage service identity")
            continue
        names.append(name)
        if icon_for(name, mapping) is None:
            missing_icons += 1
    if missing_icons:
        errors.append(f"unmapped Component/Resource/API identities: {missing_icons}")
    stats.update(entities=len(entities), services=len(identities),
                 icons=len(mapping), missing_icons=missing_icons,
                 duplicate_names=sum(value - 1 for value in Counter(names).values() if value > 1))
    if site_generated is not None:
        try:
            text = site_generated.read_text(encoding="utf-8")
            if text.count(TS_EXPORT) != 1:
                raise ValueError("missing generated TypeScript export")
            body = text.split(TS_EXPORT, 1)[1].split(";", 1)[0].strip()
            site_mapping = json.loads(body)
            if site_mapping != mapping:
                errors.append("site generated icon mapping differs from Compose webAssets")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"site mapping unreadable or malformed: {type(exc).__name__}")
    return errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--site-generated", type=Path, default=None)
    args = parser.parse_args(argv)
    errors, stats = audit(args.root, args.site_generated)
    for error in errors:
        print("FAIL " + error, file=sys.stderr)
    if errors:
        return 1
    print("PASS canonical catalog / icon contract: " + " ".join(
        f"{key}={value}" for key, value in sorted(stats.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
