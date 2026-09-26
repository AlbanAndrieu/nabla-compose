from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one or more combined P0.3 runtime-env and Backstage "
            "migration bundles without reading secret values."
        )
    )
    parser.add_argument(
        "--app",
        action="append",
        required=True,
        help="Application directory under apps/. Repeat for multiple applications.",
    )
    return parser.parse_args()


def entity_ref(entity: dict[str, Any]) -> str:
    kind = str(entity.get("kind") or "").strip().lower()
    metadata = entity.get("metadata") or {}
    namespace = str(metadata.get("namespace") or "default").strip().lower()
    name = str(metadata.get("name") or "").strip().lower()
    if not kind or not name:
        raise ValueError("Backstage entity requires kind and metadata.name")
    return f"{kind}:{namespace}/{name}"


def label_map(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    result: dict[str, str] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, value = item.split("=", 1)
            result[key] = value
    return result


def env_paths(service: dict[str, Any]) -> list[str]:
    raw = service.get("env_file") or []
    if isinstance(raw, str):
        raw = [raw]
    paths: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict) and entry.get("path"):
            paths.append(str(entry["path"]))
    return paths


def manifest_apps() -> set[str]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    apps: set[str] = set()
    for value in payload.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            if isinstance(entry, dict) and entry.get("app"):
                apps.add(str(entry["app"]))
    return apps


def check_app(app: str, managed_secret_apps: set[str]) -> list[str]:
    errors: list[str] = []
    app_dir = ROOT / "apps" / app
    compose_path = app_dir / "compose.yml"
    catalog_path = app_dir / "catalog-info.yaml"

    if not compose_path.is_file():
        return [f"{app}: missing {compose_path.relative_to(ROOT)}"]
    if not catalog_path.is_file():
        return [f"{app}: missing {catalog_path.relative_to(ROOT)}"]

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    project_name = str(compose.get("name") or "").strip()
    if project_name != app:
        errors.append(
            f"{app}: Compose project name must be {app!r}, got {project_name!r}"
        )

    services = compose.get("services") or {}
    if not isinstance(services, dict):
        return errors + [f"{app}: Compose services must be a mapping"]

    entities: dict[str, str] = {}
    try:
        documents = yaml.safe_load_all(catalog_path.read_text(encoding="utf-8"))
        for document in documents:
            if not isinstance(document, dict):
                continue
            ref = entity_ref(document)
            name = ref.split("/", 1)[1]
            if name in entities:
                errors.append(
                    f"{app}: duplicate Backstage metadata.name {name!r} "
                    f"({entities[name]} and {ref})"
                )
            entities[name] = ref
    except (ValueError, yaml.YAMLError) as exc:
        errors.append(f"{app}: invalid catalog-info.yaml: {exc}")
        return errors

    canonical_prefix = f"/mnt/cpool/secrets/runtime/{app}/"
    has_runtime_env = False

    for service_name, service_raw in services.items():
        if not isinstance(service_raw, dict):
            continue
        paths = env_paths(service_raw)
        if paths:
            has_runtime_env = True
        for path in paths:
            if not path.startswith(canonical_prefix):
                errors.append(
                    f"{app}:{service_name}: env_file {path!r} is outside "
                    f"{canonical_prefix}"
                )

        metadata = service_raw.get("x-nabla")
        if not isinstance(metadata, dict):
            continue
        service_id = str(metadata.get("id") or service_name).strip().lower()
        expected_ref = entities.get(service_id)
        if expected_ref is None:
            errors.append(
                f"{app}:{service_name}: x-nabla.id {service_id!r} has no "
                "matching Backstage entity"
            )
            continue

        actual_ref = label_map(service_raw.get("labels")).get(
            "com.albandrieu.nabla.entity-ref"
        )
        if actual_ref != expected_ref:
            errors.append(
                f"{app}:{service_name}: expected entity-ref label {expected_ref!r}, "
                f"got {actual_ref!r}"
            )

    if has_runtime_env and app not in managed_secret_apps:
        errors.append(
            f"{app}: canonical runtime env is used but config/secrets/manifest.json "
            "has no app metadata"
        )

    return errors


def main() -> int:
    args = parse_args()
    managed_secret_apps = manifest_apps()
    failed = False

    for app in dict.fromkeys(args.app):
        errors = check_app(app, managed_secret_apps)
        if errors:
            failed = True
            for error in errors:
                print(f"ERROR: {error}")
            continue
        print(f"OK: {app}: P0.3 runtime-env + Backstage migration bundle")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
