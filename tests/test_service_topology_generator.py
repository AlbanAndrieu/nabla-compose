"""Focused tests for the declared service-topology generator contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate-service-topology.py"
SPEC = importlib.util.spec_from_file_location("generate_service_topology", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ServiceTopologyGeneratorTest(unittest.TestCase):
    def test_hosted_by_is_a_supported_relation_type(self) -> None:
        relation = MODULE.topology_relation(
            {
                "target": "docker",
                "type": "hostedBy",
                "strength": "required",
                "description": "Workload is placed on the Docker runtime.",
            },
            "openwebui",
            "apps/openwebui/compose.yml",
            0,
            "fixture.relations[0]",
        )

        self.assertEqual(relation["source"], "openwebui")
        self.assertEqual(relation["target"], "docker")
        self.assertEqual(relation["type"], "hostedBy")
        self.assertEqual(relation["strength"], "required")
        self.assertTrue(relation["evidence"])

    def test_truenas_compose_runtime_derives_hosted_by_docker(self) -> None:
        relation = MODULE.runtime_placement_relation(
            {
                "id": "openwebui",
                "composeService": "open-webui",
                "runtime": {
                    "provider": "truenas-app",
                    "containerService": "open-webui",
                },
            },
            "apps/openwebui/compose.yml",
        )

        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(
            (relation["source"], relation["target"], relation["type"]),
            ("openwebui", "docker", "hostedBy"),
        )
        self.assertEqual(relation["strength"], "required")
        self.assertEqual(
            relation["evidence"],
            [
                "apps/openwebui/compose.yml:"
                "open-webui.x-nabla.runtime.containerService"
            ],
        )

    def test_non_compose_runtime_does_not_derive_docker_placement(self) -> None:
        relation = MODULE.runtime_placement_relation(
            {
                "id": "native-app",
                "composeService": "native-app",
                "runtime": {"provider": "truenas-app", "appId": "native-app"},
            },
            "apps/native/compose.yml",
        )

        self.assertIsNone(relation)

    def test_document_level_relation_requires_explicit_source(self) -> None:
        relation = MODULE.document_topology_relation(
            {
                "source": "docker",
                "target": "truenas",
                "type": "hostedBy",
                "strength": "required",
            },
            "apps/homarr/compose.yml",
            0,
            "fixture.x-nabla.relations[0]",
        )

        self.assertEqual(
            (relation["source"], relation["target"], relation["type"]),
            ("docker", "truenas", "hostedBy"),
        )

    def test_undeclared_compose_helpers_do_not_become_catalog_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            relative_path = Path("apps/fixture/compose.yml")
            compose_path = root / relative_path
            compose_path.parent.mkdir(parents=True)
            compose_path.write_text(
                """
services:
  declared:
    image: example/declared:latest
    x-nabla:
      id: declared
      name: Declared service
      kind: application
      category: test
      runtime:
        provider: truenas-app
        containerService: declared
  helper:
    image: example/helper:latest
    depends_on:
      - declared
""".lstrip(),
                encoding="utf-8",
            )

            nodes: dict[str, dict] = {}
            relations: dict[tuple[str, str, str], dict] = {}
            services: dict[str, dict] = {}
            with (
                patch.object(MODULE, "ROOT", root),
                patch.object(
                    MODULE,
                    "tracked_compose_paths",
                    return_value=[relative_path],
                ),
            ):
                MODULE.load_compose_extensions(nodes, relations, services)

        self.assertEqual(set(nodes), {"declared"})
        self.assertEqual(set(services), {"declared"})
        self.assertNotIn("helper", nodes)
        self.assertNotIn("helper", services)
        self.assertIn(("declared", "docker", "hostedBy"), relations)

    def test_presentation_role_and_criticality_propagate_to_service(self) -> None:
        metadata = {
            "id": "vaultwarden",
            "name": "Vaultwarden",
            "kind": "security-app",
            "category": "security",
            "presentationRole": "service",
            "criticality": "medium",
            "runtime": {
                "provider": "truenas-app",
                "containerService": "vaultwarden",
            },
        }

        node = MODULE.topology_node(
            metadata,
            "apps/vaultwarden/compose.yml",
            "fixture.x-nabla",
        )
        service = MODULE.declared_service(
            metadata,
            "apps/vaultwarden/compose.yml",
            "vaultwarden",
            "fixture.x-nabla",
        )

        self.assertEqual(node["presentationRole"], "service")
        self.assertEqual(node["criticality"], "medium")
        self.assertEqual(service["presentationRole"], "service")
        self.assertEqual(service["criticality"], "medium")

    def test_core_role_is_normalized_to_critical(self) -> None:
        metadata = {
            "id": "kubernetes",
            "name": "Kubernetes",
            "kind": "orchestrator",
            "category": "infrastructure",
            "presentationRole": "core",
        }

        node = MODULE.topology_node(
            metadata,
            "catalog/service-topology.static.json",
            "fixture.x-nabla",
        )

        self.assertEqual(node["presentationRole"], "core")
        self.assertEqual(node["criticality"], "critical")

    def test_core_role_rejects_noncritical_criticality(self) -> None:
        metadata = {
            "id": "kubernetes",
            "name": "Kubernetes",
            "kind": "orchestrator",
            "category": "infrastructure",
            "presentationRole": "core",
            "criticality": "high",
        }

        with self.assertRaisesRegex(
            ValueError,
            "criticality must be critical when presentationRole is core",
        ):
            MODULE.topology_node(
                metadata,
                "catalog/service-topology.static.json",
                "fixture.x-nabla",
            )

    def test_standard_is_not_a_valid_criticality(self) -> None:
        metadata = {
            "id": "fixture",
            "name": "Fixture",
            "kind": "application",
            "category": "test",
            "criticality": "standard",
        }

        with self.assertRaisesRegex(ValueError, "criticality must be one of"):
            MODULE.topology_node(
                metadata,
                "apps/fixture/compose.yml",
                "fixture.x-nabla",
            )

    def test_invalid_presentation_metadata_is_rejected(self) -> None:
        base = {
            "id": "fixture",
            "name": "Fixture",
            "kind": "application",
            "category": "test",
        }

        with self.assertRaisesRegex(ValueError, "presentationRole must be one of"):
            MODULE.topology_node(
                {**base, "presentationRole": "dashboard-only"},
                "apps/fixture/compose.yml",
                "fixture.x-nabla",
            )

        with self.assertRaisesRegex(ValueError, "criticality must be one of"):
            MODULE.topology_node(
                {**base, "criticality": "catastrophic"},
                "apps/fixture/compose.yml",
                "fixture.x-nabla",
            )

    def test_unknown_relation_type_is_rejected_before_generation(self) -> None:
        with self.assertRaisesRegex(ValueError, "type must be one of"):
            MODULE.topology_relation(
                {
                    "target": "docker",
                    "type": "inventedByUI",
                    "strength": "required",
                },
                "openwebui",
                "apps/openwebui/compose.yml",
                0,
                "fixture.relations[0]",
            )


if __name__ == "__main__":
    unittest.main()
