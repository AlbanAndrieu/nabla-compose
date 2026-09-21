from __future__ import annotations

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _documents(path: Path) -> list[dict]:
    documents = [
        item
        for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if item is not None
    ]
    if not all(isinstance(item, dict) for item in documents):
        raise AssertionError(f"{path.relative_to(ROOT)} contains a non-mapping document")
    return documents


def _entity_ref(entity: dict) -> str:
    kind = str(entity["kind"]).lower()
    namespace = str(entity.get("metadata", {}).get("namespace") or "default")
    name = str(entity["metadata"]["name"])
    return f"{kind}:{namespace}/{name}"


def _labels(service: dict) -> dict[str, str]:
    raw = service.get("labels") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    result: dict[str, str] = {}
    for item in raw:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


class CatalogV2PilotTests(unittest.TestCase):
    def test_pilot_backstage_entities_have_unique_full_refs(self) -> None:
        paths = [
            ROOT / "catalog" / "catalog-info.yaml",
            ROOT / "apps" / "neo4j" / "catalog-info.yaml",
            ROOT / "apps" / "cartography" / "catalog-info.yaml",
            ROOT / "apps" / "sample" / "catalog-info.yaml",
            ROOT / "apps" / "traefik" / "catalog-info.yaml",
            ROOT / "apps" / "postgres" / "catalog-info.yaml",
        ]
        refs = [_entity_ref(entity) for path in paths for entity in _documents(path)]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertIn("resource:default/postgresql", refs)
        self.assertIn("resource:default/neo4j-security", refs)
        self.assertIn("resource:default/cloudflare-tunnel", refs)
        self.assertIn("component:default/fastapi-sample", refs)
        self.assertIn("component:default/cartography", refs)
        self.assertIn("component:default/traefik", refs)
        self.assertIn("component:default/postgres-exporter", refs)

    def test_cartography_declares_one_future_backstage_dependency(self) -> None:
        entity = _documents(ROOT / "apps" / "cartography" / "catalog-info.yaml")[0]
        self.assertEqual(
            entity["spec"]["dependsOn"],
            ["resource:default/neo4j-security"],
        )

        compose = yaml.safe_load(
            (ROOT / "apps" / "cartography" / "compose.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(compose["name"], "cartography")
        service = compose["services"]["cartography"]
        self.assertEqual(
            _labels(service)["com.albandrieu.nabla.entity-ref"],
            "component:default/cartography",
        )
        # v1 remains until the coordinated cutover so the current generator is not
        # silently changed by the pilot.
        self.assertEqual(
            service["x-nabla"]["relations"][0]["target"],
            "neo4j-security",
        )

    def test_neo4j_uses_named_long_syntax_ports_and_entity_ref(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "apps" / "neo4j" / "compose.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(compose["name"], "neo4j")
        service = compose["services"]["neo4j-security"]
        self.assertEqual(
            _labels(service)["com.albandrieu.nabla.entity-ref"],
            "resource:default/neo4j-security",
        )
        ports = {item["name"]: item for item in service["ports"]}
        self.assertEqual(ports["web"]["target"], 7474)
        self.assertEqual(ports["web"]["published"], "31086")
        self.assertEqual(ports["web"]["app_protocol"], "http")
        self.assertEqual(ports["bolt"]["target"], 7687)
        self.assertEqual(ports["bolt"]["published"], "31087")
        self.assertEqual(ports["bolt"]["app_protocol"], "bolt")

    def test_sample_preserves_desired_public_security_intent(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(compose["name"], "sample")
        service = compose["services"]["fastapi-sample"]
        self.assertEqual(
            _labels(service)["com.albandrieu.nabla.entity-ref"],
            "component:default/fastapi-sample",
        )

        exposure = service["x-nabla"]["exposure"]
        self.assertEqual(len(exposure), 1)
        route = exposure[0]
        self.assertEqual(route["hostnames"], ["sample.albandrieu.com"])
        self.assertEqual(route["protocol"], "HTTPS")
        self.assertEqual(route["visibility"], "public")
        self.assertEqual(
            route["gatewayRef"],
            "resource:default/cloudflare-tunnel",
        )
        self.assertEqual(route["backendPort"], "web")
        self.assertTrue(route["access"]["required"])

        port = service["ports"][0]
        self.assertEqual(port["name"], "web")
        self.assertEqual(port["target"], 8080)
        self.assertEqual(port["app_protocol"], "http")

    def test_postgres_resource_and_exporter_are_not_conflated(self) -> None:
        static_refs = {
            _entity_ref(entity): entity
            for entity in _documents(ROOT / "catalog" / "catalog-info.yaml")
        }
        postgres = static_refs["resource:default/postgresql"]
        self.assertEqual(postgres["spec"]["type"], "database")

        exporter = _documents(
            ROOT / "apps" / "postgres" / "catalog-info.yaml"
        )[0]
        self.assertEqual(_entity_ref(exporter), "component:default/postgres-exporter")
        self.assertEqual(
            exporter["spec"]["dependsOn"],
            ["resource:default/postgresql"],
        )

        compose = yaml.safe_load(
            (ROOT / "apps" / "postgres" / "compose.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(compose["name"], "postgres")
        service = compose["services"]["postgres_exporter"]
        self.assertEqual(
            _labels(service)["com.albandrieu.nabla.entity-ref"],
            "component:default/postgres-exporter",
        )
        self.assertEqual(service["ports"][0]["name"], "metrics")

    def test_traefik_pilot_has_stable_project_entity_and_named_ports(self) -> None:
        compose = yaml.safe_load(
            (ROOT / "apps" / "traefik" / "compose.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(compose["name"], "traefik")
        service = compose["services"]["traefik"]
        self.assertEqual(
            _labels(service)["com.albandrieu.nabla.entity-ref"],
            "component:default/traefik",
        )
        ports = {item["name"]: item for item in service["ports"]}
        self.assertEqual(set(ports), {"web", "websecure", "dashboard", "metrics"})
        self.assertEqual(ports["websecure"]["app_protocol"], "https")


if __name__ == "__main__":
    unittest.main()
