#!/usr/bin/env python3
"""Audit Compose secret usage against the metadata-only Vaultwarden manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "config" / "secrets" / "manifest.json"
APPS_ROOT = ROOT / "apps"

SECRET_NAME = re.compile(
    r"(?:PASSWORD|PASSWD|TOKEN|SECRET|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL|AUTH|DSN|DATABASE_URL|REDIS_URL)",
    re.IGNORECASE,
)
VAR_REF = re.compile(r"\$\{([A-Z][A-Z0-9_]*)[^}]*\}")
DANGEROUS_DEFAULT = re.compile(
    r"(?i)(changeme|secretpassword|chooseaverystrongpassword|password123|admin123)"
)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def env_file_paths(service: dict[str, Any]) -> list[str]:
    raw = service.get("env_file") or []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    paths: list[str] = []
    for item in raw:
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def environment_pairs(service: dict[str, Any]) -> list[tuple[str, str]]:
    raw = service.get("environment") or {}
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            pairs.append((str(key), "" if value is None else str(value)))
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str):
                continue
            key, _, value = item.partition("=")
            pairs.append((key, value))
    return pairs


def manifest_index(manifest: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]]]:
    fields: dict[str, set[str]] = {}
    entries: dict[str, list[dict[str, Any]]] = {}
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        service = str(item.get("service") or item.get("app") or "")
        if not service:
            continue
        fields.setdefault(service, set()).update(
            str(secret.get("env"))
            for secret in item.get("secrets", [])
            if isinstance(secret, dict) and secret.get("env")
        )
        entries.setdefault(service, []).append(item)
    return fields, entries


def classify_env_path(path: str) -> str:
    if path.startswith("/mnt/cpool/secrets/runtime/"):
        return "canonical"
    if path.startswith("/mnt/cpool/"):
        return "legacy-host"
    if path.startswith(".") or not path.startswith("/"):
        return "repository-local"
    return "external"


def audit_app(
    app: str,
    compose: Path,
    manifest_fields: dict[str, set[str]],
    manifest_entries: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    data = load_yaml(compose)
    services = data.get("services") or {}
    env_files: set[str] = set()
    candidates: set[str] = set()
    dangerous: list[str] = []

    if isinstance(services, dict):
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            env_files.update(env_file_paths(service))
            for key, value in environment_pairs(service):
                if SECRET_NAME.search(key):
                    candidates.add(key)
                for ref in VAR_REF.findall(value):
                    if SECRET_NAME.search(ref):
                        candidates.add(ref)
                if DANGEROUS_DEFAULT.search(value):
                    dangerous.append(f"{service_name}:{key}")

    covered = manifest_fields.get(app, set())
    return {
        "app": app,
        "compose": str(compose.relative_to(ROOT)),
        "envFiles": [
            {"path": path, "class": classify_env_path(path)}
            for path in sorted(env_files)
        ],
        "secretCandidates": sorted(candidates),
        "manifestFields": sorted(covered),
        "uncoveredCandidates": sorted(candidates - covered),
        "dangerousDefaults": sorted(set(dangerous)),
        "manifestEntries": [
            {
                "app": str(item.get("app")),
                "item": str(item.get("item")),
                "runtimeFile": str(item.get("runtimeFile") or ".env.secrets"),
            }
            for item in manifest_entries.get(app, [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--app", action="append", dest="apps")
    parser.add_argument(
        "--fail-on-dangerous-defaults",
        action="store_true",
        help="return non-zero when a scanned Compose contains a known unsafe placeholder",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_fields, manifest_entries = manifest_index(manifest)
    requested = set(args.apps or [])
    results: list[dict[str, Any]] = []

    for compose in sorted(APPS_ROOT.glob("*/compose.yml")):
        app = compose.parent.name
        if requested and app not in requested:
            continue
        results.append(
            audit_app(app, compose, manifest_fields, manifest_entries)
        )

    if args.json:
        print(json.dumps({"services": results}, indent=2, sort_keys=True))
    else:
        print(
            "APP\tLEGACY_ENV_FILES\tUNCOVERED_SECRET_CANDIDATES\tDANGEROUS_DEFAULTS"
        )
        for row in results:
            legacy = ",".join(
                item["path"]
                for item in row["envFiles"]
                if item["class"] != "canonical"
            )
            print(
                f"{row['app']}\t{legacy or '-'}\t"
                f"{','.join(row['uncoveredCandidates']) or '-'}\t"
                f"{','.join(row['dangerousDefaults']) or '-'}"
            )

    if args.fail_on_dangerous_defaults and any(
        row["dangerousDefaults"] for row in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
