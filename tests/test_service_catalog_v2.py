from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate-service-catalog-v2.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("service_catalog_v2", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load service catalog v2 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceCatalogV2ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = load_generator()
        cls.services = json.loads(
            (ROOT / "catalog" / "services.json").read_text(encoding="utf-8")
        )
        cls.topology = json.loads(
            (ROOT / "catalog" / "service-topology.json").read_text(encoding="utf-8")
        )
        cls.catalog = cls.generator.build_v2(cls.services, cls.topology)

    def test_every_topology_node_has_one_stable_v2_identity(self) -> None:
        entities = self.catalog["entities"]
        self.assertEqual(len(entities), len(self.topology["nodes"]))
        ids = [entity["id"] for entity in entities]
        refs = [entity["ref"] for entity in entities]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(refs), len(set(refs)))
        for entity in entities:
            self.assertEqual(
                entity["ref"], entity["standards"]["cyclonedx"]["bomRef"]
            )
            self.assertTrue(
                entity["standards"]["backstage"]["entityRef"].startswith(
                    ("component:default/", "resource:default/")
                )
            )
            self.assertEqual(
                entity["integrations"]["cartography"]["joinProperty"], "nabla_ref"
            )
            self.assertEqual(
                entity["integrations"]["cartography"]["joinValue"], entity["ref"]
            )

    def test_v2_relations_preserve_evidence_and_resolve_refs(self) -> None:
        refs = {entity["ref"] for entity in self.catalog["entities"]}
        self.assertEqual(len(self.catalog["relations"]), len(self.topology["relations"]))
        for relation in self.catalog["relations"]:
            self.assertIn(relation["sourceRef"], refs)
            self.assertIn(relation["targetRef"], refs)
            self.assertTrue(relation["evidence"])
            self.assertIn(relation["strength"], {"required", "optional"})

    def test_backstage_projection_is_lossless_for_required_dependencies(self) -> None:
        documents = self.generator.build_backstage(self.catalog)
        self.assertEqual(len(documents), len(self.catalog["entities"]) + 3)
        generated = {
            document["metadata"]["name"]: document
            for document in documents
            if document["kind"] in {"Component", "Resource"}
        }
        self.assertEqual(len(generated), len(self.catalog["entities"]))

        neo4j = generated["neo4j-security"]
        cartography = generated["cartography"]
        self.assertIn(
            neo4j["metadata"]["annotations"]["nabla.dev/ref"],
            cartography["spec"].get("dependsOn", []),
        )

    def test_cyclonedx_projection_references_every_service(self) -> None:
        bom = self.generator.build_cyclonedx(self.catalog)
        self.assertEqual(bom["specVersion"], "1.7")
        service_refs = {service["bom-ref"] for service in bom["services"]}
        self.assertEqual(len(service_refs), len(self.catalog["entities"]))
        self.assertEqual(
            service_refs,
            {dependency["ref"] for dependency in bom["dependencies"]},
        )
        for dependency in bom["dependencies"]:
            self.assertTrue(set(dependency["dependsOn"]).issubset(service_refs))

    def test_generator_outputs_are_committed_and_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
