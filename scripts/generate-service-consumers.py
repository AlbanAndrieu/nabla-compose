#!/usr/bin/env python3
"""Generate Homarr, Gatus and AutoKuma consumer configs from apps Compose files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = ROOT / "apps" / "homarr" / "overrides.yaml"
HOMARR_OUTPUT = ROOT / "apps" / "homarr" / "generated-apps.json"
GATUS_OUTPUT = ROOT / "apps" / "gatus" / "generated-endpoints.yaml"
AUTOKUMA_OUTPUT = ROOT / "apps" / "autokuma" / "static" / "generated.json"
REPORT_OUTPUT = ROOT / "apps" / "service-consumers-report.json"
COMPOSE_RE = re.compile(r"^apps/[^/]+/(?:compose|docker-compose)(?:\.[^.]+)?\.ya?ml$")
ENV_DEFAULT_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]+)\}$")
TRAEFIK_HOST_RE = re.compile(r"Host\([`\"]([^`\"]+)[`\"]\)")
SLUG_RE = re.compile(r"[^a-z0-9]+")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def slug(value: str) -> str:
    return SLUG_RE.sub("-", value.lower()).strip("-") or "service"


def title(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def tracked_compose_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "apps/**/*.yml", "apps/**/*.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(Path(line) for line in result.stdout.splitlines() if COMPOSE_RE.match(line))


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def resolve_scalar(value: object) -> str | None:
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return None
    value = value.strip().strip('"').strip("'")
    match = ENV_DEFAULT_RE.match(value)
    if match:
        return match.group(1)
    return value if value and "${" not in value else None


def labels_as_strings(service: dict[str, Any]) -> list[str]:
    labels = service.get("labels", [])
    if isinstance(labels, dict):
        return [f"{key}={value}" for key, value in labels.items()]
    if isinstance(labels, list):
        return [str(item) for item in labels]
    return []


def traefik_url(service: dict[str, Any]) -> str | None:
    labels = labels_as_strings(service)
    for label in labels:
        if ".rule=" not in label:
            continue
        match = TRAEFIK_HOST_RE.search(label)
        if not match:
            continue
        host = match.group(1)
        secure = any(
            token in other.lower()
            for other in labels
            for token in ("tls=true", "entrypoints=websecure", "entrypoints=https")
        )
        return f"{'https' if secure else 'http'}://{host}"
    return None


def published_ports(service: dict[str, Any]) -> list[tuple[str | None, int, int | None]]:
    result: list[tuple[str | None, int, int | None]] = []
    for raw in service.get("ports", []) or []:
        if isinstance(raw, dict):
            published = resolve_scalar(raw.get("published"))
            target = resolve_scalar(raw.get("target"))
            host_ip = resolve_scalar(raw.get("host_ip"))
            if published and published.isdigit():
                result.append((host_ip, int(published), int(target) if target and target.isdigit() else None))
            continue
        if not isinstance(raw, str):
            continue
        value = raw.split("/", 1)[0]
        parts = value.rsplit(":", 2)
        if len(parts) == 1:
            continue
        if len(parts) == 2:
            host_ip, published_raw, target_raw = None, parts[0], parts[1]
        else:
            host_ip, published_raw, target_raw = parts
        published = resolve_scalar(published_raw)
        target = resolve_scalar(target_raw)
        if published and published.isdigit():
            result.append((host_ip, int(published), int(target) if target and target.isdigit() else None))
    return result


def first_reachable_port(service: dict[str, Any]) -> int | None:
    for host_ip, published, _target in published_ports(service):
        if host_ip and host_ip.strip("[]") in LOOPBACK_HOSTS:
            continue
        return published
    return None


def metadata_for(app: str, service_name: str, service: dict[str, Any], service_count: int) -> dict[str, Any]:
    raw = service.get("x-nabla")
    metadata = raw if isinstance(raw, dict) else {}
    service_id = str(metadata.get("id") or (app if service_count == 1 else f"{app}-{service_name}"))
    return {
        "id": slug(service_id),
        "name": str(metadata.get("name") or title(app if service_count == 1 else service_name)),
        "kind": str(metadata.get("kind") or "application"),
        "category": str(metadata.get("category") or "uncatalogued"),
        "description": metadata.get("description"),
        "url": metadata.get("url") if isinstance(metadata.get("url"), str) else None,
        "catalogued": bool(metadata),
    }


def load_overrides() -> dict[str, Any]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def scan_services(apps_host: str, overrides: dict[str, Any]) -> list[dict[str, Any]]:
    configured = overrides.get("services", {}) if isinstance(overrides.get("services"), dict) else {}
    records: list[dict[str, Any]] = []
    for path in tracked_compose_paths():
        document = load_yaml(path)
        services = document.get("services", {})
        if not isinstance(services, dict):
            continue
        app = path.parts[1]
        count = len(services)
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            meta = metadata_for(app, str(service_name), service, count)
            override = configured.get(meta["id"], {})
            if not isinstance(override, dict):
                override = {}
            url = override.get("url") or meta["url"] or traefik_url(service)
            port = override.get("port") or first_reachable_port(service)
            monitor_type = override.get("monitorType")
            monitor_target = override.get("monitorTarget")
            if not monitor_type:
                monitor_type = "http" if url else ("tcp" if port else None)
            if not monitor_target:
                monitor_target = url if monitor_type == "http" else (f"tcp://{apps_host}:{port}" if port else None)
            records.append(
                {
                    **meta,
                    "sourcePath": path.as_posix(),
                    "composeService": str(service_name),
                    "url": url,
                    "port": int(port) if isinstance(port, int) or (isinstance(port, str) and port.isdigit()) else None,
                    "monitorType": monitor_type,
                    "monitorTarget": monitor_target,
                }
            )
    return sorted(records, key=lambda item: item["id"])


def homarr_apps(records: list[dict[str, Any]], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    apps: list[dict[str, Any]] = []
    infrastructure = overrides.get("infrastructure", [])
    if isinstance(infrastructure, list):
        for item in infrastructure:
            if isinstance(item, dict):
                apps.append(dict(item))
    for record in records:
        url = record.get("url")
        if not url:
            continue
        app = {
            "id": record["id"],
            "name": record["name"],
            "url": url,
            "category": record["category"],
            "sourcePath": record["sourcePath"],
            "managedBy": "nabla-compose",
        }
        if record.get("description"):
            app["description"] = record["description"]
        if record.get("monitorType") == "http" and record.get("monitorTarget"):
            app["pingUrl"] = record["monitorTarget"]
        apps.append(app)
    deduped = {str(item["id"]): item for item in apps if item.get("id")}
    return [deduped[key] for key in sorted(deduped)]


def gatus_endpoints(records: list[dict[str, Any]], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for record in records:
        target = record.get("monitorTarget")
        monitor_type = record.get("monitorType")
        if not target or monitor_type not in {"http", "tcp"}:
            continue
        endpoint: dict[str, Any] = {
            "name": record["name"],
            "group": record["category"],
            "url": target,
            "interval": str(overrides.get("monitorInterval", "60s")),
            "conditions": ["[STATUS] >= 200", "[STATUS] < 400"] if monitor_type == "http" else ["[CONNECTED] == true"],
        }
        endpoints.append(endpoint)
    return sorted(endpoints, key=lambda item: (item.get("group", ""), item["name"]))


def autokuma_entities(records: list[dict[str, Any]], overrides: dict[str, Any], apps_host: str) -> list[dict[str, Any]]:
    interval = int(overrides.get("autokumaInterval", 60))
    entities: list[dict[str, Any]] = []
    for record in records:
        monitor_type = record.get("monitorType")
        target = record.get("monitorTarget")
        if monitor_type == "http" and target:
            entities.append(
                {
                    "name": record["name"],
                    "type": "http",
                    "url": target,
                    "interval": interval,
                    "max_retries": 2,
                    "retry_interval": interval,
                }
            )
        elif monitor_type == "tcp" and record.get("port"):
            entities.append(
                {
                    "name": record["name"],
                    "type": "port",
                    "hostname": apps_host,
                    "port": record["port"],
                    "interval": interval,
                    "max_retries": 2,
                    "retry_interval": interval,
                }
            )
    return sorted(entities, key=lambda item: item["name"])


def render_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_yaml(payload: object) -> str:
    return "---\n" + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def expected_outputs(apps_host: str) -> dict[Path, str]:
    overrides = load_overrides()
    records = scan_services(apps_host, overrides)
    homarr = {
        "version": 1,
        "generatedFrom": "apps/**/compose*.yml",
        "appsHost": apps_host,
        "apps": homarr_apps(records, overrides),
    }
    gatus = {"endpoints": gatus_endpoints(records, overrides)}
    autokuma = autokuma_entities(records, overrides, apps_host)
    report = {
        "version": 1,
        "servicesScanned": len(records),
        "catalogued": sum(1 for record in records if record["catalogued"]),
        "homarrApps": len(homarr["apps"]),
        "gatusEndpoints": len(gatus["endpoints"]),
        "autokumaMonitors": len(autokuma),
        "withoutNavigationUrl": [record["id"] for record in records if not record.get("url")],
        "withoutMonitor": [record["id"] for record in records if not record.get("monitorTarget")],
    }
    return {
        HOMARR_OUTPUT: render_json(homarr),
        GATUS_OUTPUT: render_yaml(gatus),
        AUTOKUMA_OUTPUT: render_json(autokuma),
        REPORT_OUTPUT: render_json(report),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apps-host", default="172.17.0.24")
    args = parser.parse_args()
    outputs = expected_outputs(args.apps_host)
    stale: list[Path] = []
    for path, expected in outputs.items():
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if args.check:
            if current != expected:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        for path in stale:
            print(f"{path.relative_to(ROOT)} is stale; run python scripts/generate-service-consumers.py", file=sys.stderr)
        return 1
    if args.check:
        print("Homarr, Gatus and AutoKuma consumer configs are synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
