#!/usr/bin/env python3
"""Generate Homarr, Gatus and AutoKuma consumers from app Compose files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATIC_CONFIG = ROOT / "catalog" / "service-consumers.static.yml"
HOMARR_OUTPUT = ROOT / "apps" / "homarr" / "generated" / "apps.json"
GATUS_OUTPUT = ROOT / "apps" / "gatus" / "config" / "config.yml"
AUTOKUMA_OUTPUT = ROOT / "apps" / "autokuma" / "static" / "generated-monitors.json"

IDENTIFIER_RE = re.compile(r"[^a-z0-9]+")
COMPOSE_DEFAULT_RE = re.compile(
    r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-|-)([^}]*)\}"
)
TRAEFIK_HOST_RE = re.compile(r"Host\(`([^`]+)`\)")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

NON_UI_KINDS = {
    "cache",
    "database",
    "ids",
    "log-store",
    "metrics-exporter",
    "metrics-store",
    "model-runtime",
    "search",
    "security-agent",
    "service",
    "telemetry-collector",
    "trace-store",
    "worker",
}
UI_KINDS = {
    "application",
    "automation",
    "code-quality",
    "dashboard",
    "log-management",
    "network-observability",
    "observability",
    "observability-ui",
    "status-monitor",
}
WEB_PORT_SCHEMES = {
    80: "http",
    443: "https",
    3000: "http",
    3001: "https",
    3002: "http",
    3003: "https",
    3050: "http",
    4040: "http",
    5601: "http",
    7575: "http",
    7860: "http",
    8080: "http",
    8081: "http",
    8082: "http",
    8083: "http",
    8085: "http",
    8090: "http",
    8123: "http",
    8443: "https",
    8888: "http",
    9001: "http",
    9090: "http",
    9443: "https",
    20720: "http",
    30132: "https",
}


def fail(message: str) -> None:
    raise ValueError(message)


def slug(value: object) -> str:
    text = str(value or "").strip().lower()
    text = IDENTIFIER_RE.sub("-", text).strip("-")
    return text or "service"


def title(value: str) -> str:
    parts = re.split(r"[-_]+", value)
    return " ".join(part.capitalize() for part in parts if part)


def tracked_compose_paths() -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "apps/*/compose*.yml",
            "apps/*/compose*.yaml",
            "apps/*/docker-compose*.yml",
            "apps/*/docker-compose*.yaml",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(Path(line) for line in result.stdout.splitlines() if line.strip())


def load_static() -> dict[str, Any]:
    data = yaml.safe_load(STATIC_CONFIG.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("version") != 1:
        fail("catalog/service-consumers.static.yml must contain version: 1")
    return data


def concrete_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or "${" in value:
        return None
    return value


def resolve_compose_defaults(value: object) -> str | None:
    """Resolve only literal defaults in ${VAR:-x}/${VAR-x}; never read env."""
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = COMPOSE_DEFAULT_RE.sub(lambda match: match.group(1), text)
    return None if "${" in text else text


def published_ports(service: dict[str, Any]) -> list[dict[str, int | str]]:
    result: list[dict[str, int | str]] = []
    raw_ports = service.get("ports", [])
    if not isinstance(raw_ports, list):
        return result

    for raw in raw_ports:
        host_ip: str | None = None
        published: object | None = None
        target: object | None = None
        protocol = "tcp"

        if isinstance(raw, dict):
            host_ip = concrete_text(raw.get("host_ip"))
            published = raw.get("published")
            target = raw.get("target")
            protocol = str(raw.get("protocol", "tcp")).lower()
        elif isinstance(raw, (str, int)):
            text_value = resolve_compose_defaults(raw)
            if not text_value:
                continue
            if "/" in text_value:
                text_value, protocol = text_value.rsplit("/", 1)
                protocol = protocol.lower()
            parts = text_value.split(":")
            if len(parts) < 2:
                continue
            published, target = parts[-2], parts[-1]
            if len(parts) > 2:
                host_ip = ":".join(parts[:-2]).strip("[]")

        if protocol != "tcp" or host_ip in LOOPBACK_HOSTS:
            continue
        published_text = resolve_compose_defaults(published)
        target_text = resolve_compose_defaults(target)
        try:
            published_port = int(str(published_text))
            target_port = int(str(target_text))
        except (TypeError, ValueError):
            continue
        if not (1 <= published_port <= 65535 and 1 <= target_port <= 65535):
            continue
        result.append(
            {
                "published": published_port,
                "target": target_port,
                "protocol": protocol,
            }
        )
    return result


def label_map(service: dict[str, Any]) -> dict[str, str]:
    raw_labels = service.get("labels", {})
    if isinstance(raw_labels, dict):
        return {
            str(key): str(value)
            for key, value in raw_labels.items()
            if value is not None
        }
    if not isinstance(raw_labels, list):
        return {}
    labels: dict[str, str] = {}
    for raw in raw_labels:
        if not isinstance(raw, str) or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        labels[key] = value
    return labels


def traefik_url(service: dict[str, Any]) -> str | None:
    labels = label_map(service)
    if labels.get("traefik.enable", "").lower() not in {"1", "true", "yes"}:
        return None

    router_names: list[str] = []
    host: str | None = None
    for key, value in labels.items():
        if not key.startswith("traefik.http.routers.") or not key.endswith(".rule"):
            continue
        match = TRAEFIK_HOST_RE.search(value)
        if not match:
            continue
        host = match.group(1)
        router_names.append(key.split(".")[3])
        break
    if not host:
        return None

    secure = False
    for router in router_names:
        prefix = f"traefik.http.routers.{router}."
        tls = labels.get(prefix + "tls", "").lower()
        entrypoints = labels.get(prefix + "entrypoints", "").lower()
        secure = tls in {"1", "true", "yes"} or any(
            token in entrypoints for token in ("https", "websecure")
        )
    return f"{'https' if secure else 'http'}://{host}"


def app_service_id(
    app_name: str,
    service_name: str,
    metadata: dict[str, Any],
) -> str:
    explicit = concrete_text(metadata.get("id"))
    if explicit:
        return slug(explicit)
    app_id = slug(app_name)
    service_id = slug(service_name)
    return app_id if app_id == service_id else f"{app_id}-{service_id}"


def infer_web_url(
    host: str,
    kind: str | None,
    ports: list[dict[str, int | str]],
) -> str | None:
    if kind in NON_UI_KINDS:
        return None
    for item in ports:
        target = int(item["target"])
        published = int(item["published"])
        scheme = WEB_PORT_SCHEMES.get(target) or WEB_PORT_SCHEMES.get(published)
        if scheme:
            return f"{scheme}://{host}:{published}"
    if kind in UI_KINDS and ports:
        item = ports[0]
        target = int(item["target"])
        published = int(item["published"])
        scheme = "https" if target in {443, 8443, 9443} else "http"
        return f"{scheme}://{host}:{published}"
    return None


def parse_port_target(target: str) -> tuple[str, int] | None:
    value = target.strip()
    if value.startswith("tcp://"):
        value = value[6:]
    if ":" not in value:
        return None
    host, raw_port = value.rsplit(":", 1)
    try:
        port = int(raw_port)
    except ValueError:
        return None
    if not host or not 1 <= port <= 65535:
        return None
    return host, port


def monitor_from_metadata(
    service_id: str,
    name: str,
    category: str,
    description: str | None,
    monitoring: object,
    default_interval: str,
) -> dict[str, Any] | None:
    if not isinstance(monitoring, dict) or monitoring.get("enabled") is False:
        return None
    monitor_type = str(monitoring.get("type", "")).lower()
    group = concrete_text(monitoring.get("group")) or category
    interval = concrete_text(monitoring.get("interval")) or default_interval
    result: dict[str, Any] = {
        "id": service_id,
        "name": name,
        "group": group,
        "interval": interval,
    }
    if description:
        result["description"] = description

    if monitor_type == "http":
        target = concrete_text(monitoring.get("target")) or concrete_text(
            monitoring.get("url")
        )
        if not target or urlparse(target).scheme not in {"http", "https"}:
            fail(f"{service_id}: HTTP monitoring requires an http(s) target")
        result.update({"type": "http", "url": target})
        conditions = monitoring.get("conditions")
        if conditions is not None:
            valid = isinstance(conditions, list) and all(
                isinstance(item, str) and item.strip() for item in conditions
            )
            if not valid:
                fail(f"{service_id}: monitoring.conditions must be a list of strings")
            result["conditions"] = [item.strip() for item in conditions]
        return result

    if monitor_type in {"port", "tcp"}:
        host = concrete_text(monitoring.get("host"))
        port = monitoring.get("port")
        target = concrete_text(monitoring.get("target"))
        parsed = parse_port_target(target) if target else None
        if parsed:
            host, port = parsed
        try:
            port = int(str(port))
        except (TypeError, ValueError):
            return None
        if not host or not 1 <= port <= 65535:
            fail(f"{service_id}: port monitoring requires host and port")
        result.update({"type": "port", "host": host, "port": port})
        return result

    if monitor_type in {"icmp", "ping"}:
        host = concrete_text(monitoring.get("host")) or concrete_text(
            monitoring.get("target")
        )
        if not host:
            fail(f"{service_id}: ping monitoring requires host or target")
        result.update({"type": "ping", "host": host})
        return result

    if monitor_type:
        fail(f"{service_id}: unsupported monitoring type {monitor_type!r}")
    return None


def fallback_monitor(
    service_id: str,
    name: str,
    category: str,
    description: str | None,
    host: str,
    ports: list[dict[str, int | str]],
    default_interval: str,
) -> dict[str, Any] | None:
    if not ports:
        return None
    item = ports[0]
    result: dict[str, Any] = {
        "id": service_id,
        "name": name,
        "group": category,
        "type": "port",
        "host": host,
        "port": int(item["published"]),
        "interval": default_interval,
    }
    if description:
        result["description"] = description
    return result


def apply_homarr_static(
    homarr_apps: dict[str, dict[str, Any]],
    static: dict[str, Any],
) -> None:
    config = static.get("homarr", {})
    if not isinstance(config, dict):
        return

    for extra in config.get("extras", []):
        if not isinstance(extra, dict):
            continue
        extra_id = slug(extra.get("id"))
        href = concrete_text(extra.get("url"))
        entry: dict[str, Any] = {
            "id": extra_id,
            "name": concrete_text(extra.get("name")) or title(extra_id),
            "group": concrete_text(extra.get("category")) or "infrastructure",
            "sourcePath": "catalog/service-consumers.static.yml",
            "composeService": None,
            "dockerManaged": False,
            "href": href,
            "syncEligible": bool(href),
        }
        for key in ("description", "icon"):
            value = concrete_text(extra.get(key))
            if value:
                entry[key] = value
        homarr_apps.setdefault(extra_id, entry)

    for override in config.get("overrides", []):
        if not isinstance(override, dict):
            continue
        service_id = slug(override.get("id"))
        entry = homarr_apps.get(service_id)
        if not entry:
            continue
        for source, target in (
            ("name", "name"),
            ("category", "group"),
            ("url", "href"),
            ("description", "description"),
            ("icon", "icon"),
        ):
            value = concrete_text(override.get(source))
            if value:
                entry[target] = value
        entry["syncEligible"] = bool(entry.get("href"))


def apply_monitoring_static(
    monitors: dict[str, dict[str, Any]],
    static: dict[str, Any],
    default_interval: str,
) -> None:
    config = static.get("monitoring", {})
    if not isinstance(config, dict):
        return
    for extra in config.get("extras", []):
        if not isinstance(extra, dict):
            continue
        extra_id = slug(extra.get("id"))
        monitor = monitor_from_metadata(
            extra_id,
            concrete_text(extra.get("name")) or title(extra_id),
            concrete_text(extra.get("category")) or "infrastructure",
            concrete_text(extra.get("description")),
            {**extra, "enabled": True},
            default_interval,
        )
        if monitor:
            monitors[extra_id] = monitor


def collect_services(
    static: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    defaults = static.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    host = concrete_text(defaults.get("host")) or "172.17.0.24"
    default_interval = concrete_text(defaults.get("interval")) or "60s"
    homarr_apps: dict[str, dict[str, Any]] = {}
    monitors: dict[str, dict[str, Any]] = {}
    declared_service_ids: set[str] = set()

    for relative_path in tracked_compose_paths():
        document = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            continue
        services = document.get("services", {})
        if not isinstance(services, dict):
            continue
        app_name = relative_path.parts[1]

        for raw_service_name, raw_service in services.items():
            if not isinstance(raw_service, dict):
                continue
            service_name = str(raw_service_name)
            raw_metadata = raw_service.get("x-nabla")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            service_id = app_service_id(app_name, service_name, metadata)
            if isinstance(raw_metadata, dict):
                declared_service_ids.add(service_id)
            name = concrete_text(metadata.get("name")) or title(service_name)
            kind = concrete_text(metadata.get("kind"))
            category = concrete_text(metadata.get("category")) or slug(app_name)
            description = concrete_text(metadata.get("description"))
            icon = concrete_text(metadata.get("icon"))
            ports = published_ports(raw_service)
            href = (
                concrete_text(metadata.get("url"))
                or traefik_url(raw_service)
                or infer_web_url(host, kind, ports)
            )

            entry: dict[str, Any] = {
                "id": service_id,
                "name": name,
                "group": category,
                "sourcePath": relative_path.as_posix(),
                "composeService": service_name,
                "dockerManaged": True,
                "href": href,
                "syncEligible": bool(href),
            }
            if description:
                entry["description"] = description
            if icon:
                entry["icon"] = icon
            homarr_apps[service_id] = entry

            monitor = monitor_from_metadata(
                service_id,
                name,
                category,
                description,
                metadata.get("monitoring"),
                default_interval,
            )
            if monitor is None:
                monitor = fallback_monitor(
                    service_id,
                    name,
                    category,
                    description,
                    host,
                    ports,
                    default_interval,
                )
            if monitor:
                monitors[service_id] = monitor

    apply_homarr_static(homarr_apps, static)
    apply_monitoring_static(monitors, static, default_interval)
    for monitor_id, monitor in monitors.items():
        if monitor_id in declared_service_ids:
            monitor["service_id"] = monitor_id
    return (
        [homarr_apps[key] for key in sorted(homarr_apps)],
        [monitors[key] for key in sorted(monitors)],
    )


def homarr_payload(
    static: dict[str, Any],
    apps: list[dict[str, Any]],
) -> dict[str, Any]:
    homarr = static.get("homarr", {})
    if not isinstance(homarr, dict):
        homarr = {}
    docker = homarr.get("docker", {})
    if not isinstance(docker, dict):
        docker = {}
    return {
        "version": 1,
        "name": "Nabla Homarr reconciliation manifest",
        "dockerIntegration": {
            "hostname": concrete_text(docker.get("hostname"))
            or "docker-socket-proxy",
            "port": int(docker.get("port", 2375)),
            "network": concrete_text(docker.get("network")) or "intranet",
        },
        "applications": apps,
    }


def gatus_payload(monitors: list[dict[str, Any]]) -> dict[str, Any]:
    endpoints: list[dict[str, Any]] = []
    for monitor in monitors:
        endpoint: dict[str, Any] = {
            "name": monitor["name"],
            "group": monitor["group"],
            "interval": monitor["interval"],
            "extra-labels": {
                "nabla_monitor_id": monitor["id"],
                **(
                    {"nabla_service_id": monitor["service_id"]}
                    if monitor.get("service_id")
                    else {}
                ),
            },
        }
        if monitor["type"] == "http":
            endpoint["url"] = monitor["url"]
            endpoint["conditions"] = monitor.get(
                "conditions",
                ["[STATUS] >= 200", "[STATUS] < 400"],
            )
        elif monitor["type"] == "port":
            endpoint["url"] = f"tcp://{monitor['host']}:{monitor['port']}"
            endpoint["conditions"] = ["[CONNECTED] == true"]
        elif monitor["type"] == "ping":
            endpoint["url"] = f"icmp://{monitor['host']}"
            endpoint["conditions"] = ["[CONNECTED] == true"]
        else:
            continue
        endpoints.append(endpoint)
    return {
        "metrics": True,
        "storage": {"type": "sqlite", "path": "/data/gatus.db"},
        "endpoints": endpoints,
    }


def seconds(interval: str) -> int:
    match = re.fullmatch(r"(\d+)([smh])", interval.strip())
    if not match:
        fail(f"unsupported interval {interval!r}; use Ns, Nm or Nh")
    value = int(match.group(1))
    return value * {"s": 1, "m": 60, "h": 3600}[match.group(2)]


def autokuma_payload(monitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for monitor in monitors:
        entity: dict[str, Any] = {
            "type": "http"
            if monitor["type"] == "http"
            else ("ping" if monitor["type"] == "ping" else "port"),
            "name": monitor["name"],
            "description": monitor.get(
                "description",
                f"Nabla generated monitor: {monitor['id']}",
            ),
            "interval": seconds(monitor["interval"]),
            "max_retries": 3,
            "retry_interval": 60,
        }
        if monitor["type"] == "http":
            entity["url"] = monitor["url"]
        elif monitor["type"] == "port":
            entity["hostname"] = monitor["host"]
            entity["port"] = monitor["port"]
        elif monitor["type"] == "ping":
            entity["hostname"] = monitor["host"]
        result.append(entity)
    return result


def render_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_yaml(payload: object) -> str:
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        explicit_start=True,
    )


def write_or_check(path: Path, content: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if check:
        if current == content:
            return True
        print(
            f"{path.relative_to(ROOT)} is stale; "
            "run python scripts/generate-service-consumers.py",
            file=sys.stderr,
        )
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated consumer files are stale",
    )
    args = parser.parse_args()
    try:
        static = load_static()
        apps, monitors = collect_services(static)
        outputs = {
            HOMARR_OUTPUT: render_json(homarr_payload(static, apps)),
            GATUS_OUTPUT: render_yaml(gatus_payload(monitors)),
            AUTOKUMA_OUTPUT: render_json(autokuma_payload(monitors)),
        }
        ok = all(
            write_or_check(path, content, args.check)
            for path, content in outputs.items()
        )
    except (OSError, subprocess.CalledProcessError, ValueError, yaml.YAMLError) as exc:
        print(f"service consumer generation failed: {exc}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
