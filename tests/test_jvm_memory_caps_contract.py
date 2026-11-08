"""Every JVM-based Compose service declares a cgroup memory cap.

TrueNAS ran out of RAM on 2026-11-06 (Apps 44 GiB of 62 GiB, ZFS ARC down to
2-3 GiB, arc_prune at 100 %). Uncapped JVMs size their heap from host RAM
(Quarkus/Keycloak uses 70 % of the visible memory) and turn a leak into a
host-wide OOM. A per-service ``mem_limit`` keeps the OOM inside the cgroup.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

JVM_IMAGE = re.compile(
    r"opensearch|elasticsearch:|wazuh-indexer|nexus3|cp-kafka|keycloak/keycloak"
    r"|graylog/graylog|neo4j|sonarqube"
)
UNITS = {"k": 2**10, "m": 2**20, "g": 2**30}


def _bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+)([kmg])b?", str(value).strip().lower())
    assert match, value
    return int(match.group(1)) * UNITS[match.group(2)]


def _jvm_services() -> list[tuple[str, str, dict]]:
    found = []
    for compose in sorted(ROOT.glob("apps/*/compose.yml")):
        data = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        for name, service in (data.get("services") or {}).items():
            image = str((service or {}).get("image", ""))
            # Exporters (Go) and OpenSearch Dashboards (Node.js) are not JVMs.
            if JVM_IMAGE.search(image) and not re.search(r"exporter|dashboards", image):
                found.append((str(compose.relative_to(ROOT)), name, service))
    return found


def _max_heap(service: dict) -> int | None:
    env = service.get("environment") or {}
    values = env.values() if isinstance(env, dict) else env
    heaps = [
        _bytes(m.group(1))
        for value in values
        for m in re.finditer(r"-Xmx(\d+[kKmMgG])", str(value))
    ]
    return max(heaps) if heaps else None


def test_jvm_services_are_discovered() -> None:
    names = {name for _, name, _ in _jvm_services()}
    assert {"opensearch", "opensearch-security", "wazuh.indexer", "kafka", "keycloak"} <= names


def test_every_jvm_service_has_a_memory_cap() -> None:
    missing = [f"{path}:{name}" for path, name, svc in _jvm_services() if "mem_limit" not in svc]
    assert missing == [], missing


def test_explicit_heap_leaves_off_heap_headroom() -> None:
    for path, name, service in _jvm_services():
        heap = _max_heap(service)
        if heap is None:
            continue
        limit = _bytes(service["mem_limit"])
        assert limit - heap >= 512 * 2**20, f"{path}:{name} heap too close to mem_limit"
