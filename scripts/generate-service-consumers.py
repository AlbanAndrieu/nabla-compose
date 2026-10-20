#!/usr/bin/env python3
"""Project Backstage identity, Compose routing and native Gatus checks to consumers."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from nabla_ops.compose_paths import tracked_compose_paths as discover_compose_paths  # noqa: E402
from nabla_ops.catalog_exports import load_backstage_entities  # noqa: E402

ROOT = SCRIPTS_DIR.parent
HOMARR_COMPOSE = ROOT / "apps" / "homarr" / "compose.yml"
GATUS_DECLARED = ROOT / "config" / "monitoring" / "gatus-endpoints.yml"
HOMARR_OUTPUT = ROOT / "apps" / "homarr" / "generated" / "apps.json"
GATUS_OUTPUT = ROOT / "apps" / "gatus" / "config" / "config.yml"
AUTOKUMA_OUTPUT = ROOT / "apps" / "autokuma" / "static" / "generated-monitors.json"

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
    "network-flow-collector",
    "network-flow-controller",
    "network-flow-processor",
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


def tracked_compose_paths() -> list[Path]:
    """Discover Compose inputs in a checkout or immutable source archive."""
    return discover_compose_paths(ROOT)


def load_native_adapter_policy() -> dict[str, Any]:
    """Read Homarr Docker connector details from its Compose config."""
    compose = yaml.safe_load(HOMARR_COMPOSE.read_text(encoding="utf-8"))
    if not isinstance(compose, dict):
        fail("apps/homarr/compose.yml must contain a mapping")
    services = compose.get("services") or {}
    svc = services.get("homarr") if isinstance(services, dict) else None
    if not isinstance(svc, dict):
        fail("apps/homarr/compose.yml has no homarr service")
    env = svc.get("environment") or {}
    if not isinstance(env, dict):
        fail("Homarr environment must be a Compose mapping")
    hostname = concrete_text(env.get("DOCKER_HOSTNAMES"))
    raw_port = concrete_text(env.get("DOCKER_PORTS"))
    if not hostname or not raw_port:
        fail("Homarr Docker connector requires DOCKER_HOSTNAMES and DOCKER_PORTS")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("Homarr DOCKER_PORTS must be numeric") from exc
    networks = svc.get("networks") or []
    network = str(networks[0]) if isinstance(networks, list) and networks else None
    if not network:
        fail("Homarr must declare its Docker socket proxy network")
    host = None
    for value in svc.get("ports") or []:
        parts = str(value).split(":")
        if len(parts) == 3 and re.fullmatch(r"[0-9.]+", parts[0]):
            host = parts[0]
            break
    if not host:
        fail("Homarr published port must provide an explicit host IP")
    return {
        "defaults": {"host": host},
        "homarr": {"docker": {
            "hostname": hostname, "port": port, "network": network,
        }},
    }


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


def backstage_entities() -> dict[str, dict[str, Any]]:
    """Backstage documents alone own entity identity and declared state."""
    paths = [ROOT / "catalog" / "catalog-info.yaml"]
    paths.extend(sorted((ROOT / "apps").glob("*/catalog-info.yaml")))
    return {
        entity["entityRef"]: entity
        for entity in load_backstage_entities(path for path in paths if path.is_file())
    }


def entity_metadata(
    entity: dict[str, Any],
) -> tuple[str, str, str | None, str | None, str | None]:
    metadata = entity["metadata"]
    name = concrete_text(metadata.get("title")) or str(metadata["name"])
    tags = metadata.get("tags")
    category = (
        str(tags[0])
        if isinstance(tags, list) and tags and isinstance(tags[0], str)
        else "infrastructure"
    )
    description = concrete_text(metadata.get("description"))
    links = metadata.get("links") or []
    url = next(
        (
            concrete_text(link.get("url"))
            for link in links
            if isinstance(link, dict) and concrete_text(link.get("url"))
        ),
        None,
    )
    return name, category, description, url, str((entity.get("spec") or {}).get("type") or "")


def declared_entity_active(entity: dict[str, Any]) -> bool:
    labels = (entity.get("metadata") or {}).get("labels") or {}
    return labels.get("albandrieu.com/operational-state", "active") == "active"


def native_gatus_monitors(
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gatus YAML is the authority for probe semantics, Backstage for identity."""
    payload = yaml.safe_load(GATUS_DECLARED.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("endpoints"), list):
        fail("config/monitoring/gatus-endpoints.yml requires an endpoints array")
    by_id = {
        str(entity["metadata"]["name"]): entity
        for entity in entities.values()
        if entity.get("kind") in {"Component", "Resource", "API"}
    }
    seen: set[str] = set()
    monitors: list[dict[str, Any]] = []
    for source in payload["endpoints"]:
        if not isinstance(source, dict):
            fail("Gatus endpoints must be mappings")
        endpoint = dict(source)
        labels = dict(endpoint.get("extra-labels") or {})
        monitor_id = concrete_text(labels.get("nabla_monitor_id"))
        if not monitor_id:
            fail("Gatus endpoint requires extra-labels.nabla_monitor_id")
        if monitor_id in seen:
            fail(f"duplicate Gatus monitor identifier {monitor_id}")
        seen.add(monitor_id)
        service_id = concrete_text(labels.get("nabla_service_id"))
        entity = by_id.get(service_id) if service_id else None
        if entity and not declared_entity_active(entity):
            continue
        if entity:
            labels["nabla_entity_ref"] = entity["entityRef"]
        endpoint["extra-labels"] = labels
        url = concrete_text(endpoint.get("url"))
        name = concrete_text(endpoint.get("name"))
        group = concrete_text(endpoint.get("group"))
        interval = concrete_text(endpoint.get("interval"))
        if not all((url, name, group, interval)):
            fail(f"Gatus endpoint {monitor_id} missing url/name/group/interval")
        monitor: dict[str, Any] = {
            "id": monitor_id,
            "name": name,
            "group": group,
            "interval": interval,
            "gatus_endpoint": endpoint,
        }
        if service_id:
            monitor["service_id"] = service_id
        if url.startswith(("http://", "https://")):
            monitor.update({"type": "http", "url": url})
        elif url.startswith("tcp://"):
            parsed = parse_port_target(url)
            if not parsed:
                fail(f"Gatus endpoint {monitor_id}: invalid TCP URL")
            monitor.update({"type": "port", "host": parsed[0], "port": parsed[1]})
        elif url.startswith("icmp://"):
            monitor.update({"type": "ping", "host": url.removeprefix("icmp://")})
        else:
            fail(f"Gatus endpoint {monitor_id}: unsupported AutoKuma URL scheme")
        if entity:
            description = concrete_text(entity["metadata"].get("description"))
            if description:
                monitor["description"] = description
        monitors.append(monitor)
    return sorted(monitors, key=lambda item: item["id"])


def collect_services(
    static: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    defaults = static.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    host = concrete_text(defaults.get("host")) or "172.17.0.24"
    homarr_apps: dict[str, dict[str, Any]] = {}
    entities = backstage_entities()
    by_id: dict[str, dict[str, Any]] = {}
    for ref, entity in entities.items():
        if entity["kind"] not in {"Component", "Resource", "API"}:
            continue
        service_id = str(entity["metadata"]["name"])
        if service_id in by_id:
            fail(f"ambiguous Backstage service id {service_id!r}")
        by_id[service_id] = entity

    for relative_path in tracked_compose_paths():
        document = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            continue
        services = document.get("services", {})
        if not isinstance(services, dict):
            continue
        for raw_service_name, raw_service in services.items():
            if not isinstance(raw_service, dict):
                continue
            entity_ref = concrete_text(
                label_map(raw_service).get("com.albandrieu.nabla.entity-ref")
            )
            if not entity_ref:
                continue  # unmanaged support containers are not catalog entities
            entity = entities.get(entity_ref.lower())
            if entity is None:
                fail(f"{relative_path}: unresolved Backstage ref {entity_ref}")
            service_id = str(entity["metadata"]["name"])
            name, category, description, canonical_url, kind = entity_metadata(entity)
            ports = published_ports(raw_service)
            href = canonical_url or traefik_url(raw_service) or infer_web_url(host, kind, ports)
            entry: dict[str, Any] = {
                "id": service_id,
                "entityRef": entity_ref.lower(),
                "name": name,
                "group": category,
                "sourcePath": relative_path.as_posix(),
                "composeService": str(raw_service_name),
                "dockerManaged": True,
                "href": href,
                "syncEligible": bool(href),
            }
            if description:
                entry["description"] = description
            previous = homarr_apps.get(service_id)
            if previous and previous.get("entityRef") != entry["entityRef"]:
                fail(f"duplicate Homarr id {service_id!r}")
            homarr_apps[service_id] = entry

    # Non-Compose entities (pfSense/TrueNAS/Docker) are projected from their
    # Backstage standard links, without re-declaring identity in a static list.
    for service_id, entity in by_id.items():
        if service_id in homarr_apps:
            continue
        name, category, description, href, _ = entity_metadata(entity)
        if not href:
            continue
        entry = {
            "id": service_id,
            "entityRef": entity["entityRef"],
            "name": name,
            "group": category,
            "sourcePath": entity["sourcePath"],
            "composeService": None,
            "dockerManaged": False,
            "href": href,
            "syncEligible": True,
        }
        if description:
            entry["description"] = description
        homarr_apps[service_id] = entry

    # Gatus native endpoint YAML owns the probe target and conditions.
    # AutoKuma projects those same probe targets; no parallel monitoring inventory.
    monitors = {item["id"]: item for item in native_gatus_monitors(entities)}
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
    # Preserve Gatus-native conditions, intervals and custom endpoint settings.
    return {
        "metrics": True,
        "storage": {"type": "sqlite", "path": "/data/gatus.db"},
        "endpoints": [monitor["gatus_endpoint"] for monitor in monitors],
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
    # Gatus runs without DAC_OVERRIDE. On TrueNAS the generated config is
    # group-owned by "apps" (GID 568); allow only that group to read it.
    # Fix the mode on every regeneration, including pre-existing 0600 files.
    if path == GATUS_OUTPUT:
        path.chmod(0o640)
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
        static = load_native_adapter_policy()
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
