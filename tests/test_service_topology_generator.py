"""Focused tests for the declared service-topology generator contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

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
