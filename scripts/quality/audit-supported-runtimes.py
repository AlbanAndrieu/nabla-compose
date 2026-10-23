#!/usr/bin/env python3
"""Audit every declared Compose image/Dockerfile against supported runtime policy.

Offline, read-only, no Docker daemon, no registry access and no deployment.
Unknown upstream images stay UNKNOWN; never infer an embedded runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/upgrades/supported-runtime-targets.json"
IMAGE_RE = re.compile(r"^\s*image:\s*(?P<image>[^\s#]+)", re.MULTILINE)
FROM_RE = re.compile(r"^FROM\s+(?P<image>[^\s]+)", re.MULTILINE | re.IGNORECASE)
EXPLICIT_RE = re.compile(r"(?:^|[/:])(?P<runtime>python|php):(?P<version>[0-9]+\.[0-9]+)(?:\.(?P<patch>[0-9]+))?(?:[-@]|$)")
TEMPLATED_TAG_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]+)\}")
FLOATING = {"latest", "stable", "main-stable", "main-latest", "edge", "nightly"}
OPAQUE_PYTHON = {"litellm", "defectdojo", "docling", "langflow", "openrag", "sentry", "cyberbro", "dsomm", "netbox", "cartography"}
OPAQUE_PHP = {"2fauth", "wordpress", "freshrss", "nextcloud", "drupal", "mediawiki", "phpmyadmin"}


def normalized_image(raw: str) -> str:
    """Resolve ONLY an explicitly declared Compose default, never real secrets."""
    stripped = raw.strip().strip("'\"")
    return TEMPLATED_TAG_RE.sub(lambda m: m.group(1), stripped)


def _image_status(image: str, policy: dict[str, Any]) -> tuple[str, str]:
    if image.startswith("$") or image.startswith("${"):
        return "unknown", "unresolved-image-variable"
    repository, _, tag = image.partition("@")
    if not tag:
        # The last ':' after the final slash is an image tag, not a port.
        tag = repository.rsplit(":", 1)[1] if ":" in repository.rsplit("/", 1)[-1] else "latest"
    family = repository.rsplit("/", 1)[-1].split(":")[0].lower()
    runtime = "python" if family == "python" else "php" if family == "php" else ""
    match = EXPLICIT_RE.search(image)
    if match:
        runtime = match.group("runtime")
        version = match.group("version")
        cfg = policy["languageRuntimes"][runtime]
        if version in cfg["eolAtDate"]:
            return "eol", runtime + " " + version
        minimum = cfg.get("minimumPatched", {}).get(version)
        if minimum:
            patch = match.group("patch")
            if patch is None:
                return "unverified-patch", runtime + " " + version + " patch not pinned"
            selected = tuple(int(part) for part in (version + "." + patch).split("."))
            required = tuple(int(part) for part in minimum.split("."))
            if selected < required:
                return "critical-patch-missing", runtime + " needs >= " + minimum
        if version in cfg["securityOnly"]:
            return "security-only", runtime + " " + version
        if version in cfg["allowedSupported"]:
            return "supported", runtime + " " + version
        return "unknown", runtime + " " + version + " (unclassified)"
    if not runtime:
        if any(needle in image.lower() for needle in OPAQUE_PYTHON | OPAQUE_PHP):
            return "unknown", "upstream-embedded-runtime; inspect runtime image"
    if "@sha256:" in image:
        return "digest-pinned", "upstream runtime needs explicit inspection"
    if tag in FLOATING or tag == "latest" or tag.startswith("main-"):
        return "floating", "mutable upstream image tag"
    return "opaque-pinned", "upstream runtime not verifiable from image name"


def audit(root: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = sorted((root / "apps").glob("*/compose.yml"))
    paths += sorted((root / "apps").glob("**/Dockerfile"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        regex = FROM_RE if path.name == "Dockerfile" else IMAGE_RE
        for match in regex.finditer(text):
            raw = match.group("image")
            image = normalized_image(raw)
            status, note = _image_status(image, policy)
            rows.append({
                "app": path.relative_to(root).parts[1],
                "file": str(path.relative_to(root)),
                "image": image,
                "status": status,
                "note": note,
            })
    return rows


def load_policy(path: Path = POLICY) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("unsupported runtime target policy schema")
    required = {"talos", "kubernetes"}
    if not required.issubset(data.get("platform", {})):
        raise ValueError("missing platform target")
    for family in ("python", "php"):
        if family not in data.get("languageRuntimes", {}):
            raise ValueError("missing runtime support policy: " + family)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict-eol", action="store_true",
                        help="fail on EOL or known critically unpatched PHP/Python image tags")
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        rows = audit(args.root, policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("runtime audit unavailable: " + type(exc).__name__, file=sys.stderr)
        return 2
    counts = {status: sum(row["status"] == status for row in rows)
              for status in sorted({row["status"] for row in rows})}
    result = {
        "runtimeAcceptance": False,
        "scope": "repository-declarations-only",
        "declaredImages": len(rows),
        "apps": len(set(row["app"] for row in rows)),
        "counts": counts,
        "targets": {
            "talos": policy["platform"]["talos"]["target"],
            "kubernetes": policy["platform"]["kubernetes"]["target"],
            "php": policy["languageRuntimes"]["php"]["preferred"],
            "python": policy["languageRuntimes"]["python"]["preferred"],
        },
        "images": rows,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Declared services: {result['apps']}; images: {len(rows)}; targets: {result['targets']}")
        for status, count in counts.items():
            print(f"{status}: {count}")
        for row in rows:
            if row["status"] in {"eol", "critical-patch-missing", "unverified-patch", "security-only", "floating", "unknown"}:
                print(f"[{row['status']}] {row['app']} {row['image']}: {row['note']}")
    return 1 if args.strict_eol and (counts.get("eol", 0) or counts.get("critical-patch-missing", 0)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
