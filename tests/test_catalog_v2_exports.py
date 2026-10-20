from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.catalog_exports import (  # noqa: E402
    build_standard_artifacts,
    catalog_revision,
    cyclonedx_projection,
    load_backstage_entities,
    identity_mapping_projection,
)


class CatalogV2ExportTests(unittest.TestCase):
    def _fixture(self, root: Path) -> list[Path]:
        descriptor = root / "catalog-info.yaml"
        descriptor.write_text(
            """apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: database
  title: Database
spec:
  type: database
  owner: group:default/nabla-platform
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: api
  title: API
spec:
  type: service
  lifecycle: production
  owner: group:default/nabla-platform
  dependsOn:
    - resource:default/database
""",
            encoding="utf-8",
        )
        return [descriptor]

    def test_artifacts_share_one_catalog_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = build_standard_artifacts(self._fixture(Path(tmp)))

        entities = artifacts["entities.json"]
        cdx = artifacts["homelab.cdx.json"]
        self.assertEqual(entities["schemaVersion"], 2)
        self.assertEqual(cdx["specVersion"], "1.7")
        self.assertEqual(
            cdx["metadata"]["properties"][0]["value"],
            entities["catalogRevision"],
        )

    def test_cyclonedx_preserves_resolved_dependency_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = load_backstage_entities(self._fixture(Path(tmp)))
        cdx = cyclonedx_projection(entities)
        dependencies = {item["ref"]: item["dependsOn"] for item in cdx["dependencies"]}
        self.assertEqual(
            dependencies["component:default/api"],
            ["resource:default/database"],
        )
        self.assertEqual(dependencies["resource:default/database"], [])

    def test_revision_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = load_backstage_entities(self._fixture(Path(tmp)))
        self.assertEqual(catalog_revision(entities), catalog_revision(list(reversed(entities))))

    def test_organizational_entities_are_not_software_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = self._fixture(Path(tmp))
            with files[0].open("a", encoding="utf-8") as stream:
                stream.write(
                    "\n---\napiVersion: backstage.io/v1alpha1\n"
                    "kind: System\nmetadata:\n  name: homelab\n"
                    "spec:\n  owner: group:default/nabla-platform\n"
                )
            entities = load_backstage_entities(files)
        cdx = cyclonedx_projection(entities)
        refs = {entry["bom-ref"] for entry in cdx["services"]}
        self.assertEqual(refs, {"component:default/api", "resource:default/database"})
        self.assertNotIn("system:default/homelab", refs)
        self.assertEqual(
            {entry["ref"] for entry in cdx["dependencies"]}, refs
        )

    def test_explicit_native_identity_crosswalk_and_unresolved_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entities = load_backstage_entities(self._fixture(root))
            compose = root / "apps" / "demo" / "compose.yml"
            compose.parent.mkdir(parents=True)
            compose.write_text(
                "services:\n  api:\n    labels:\n"
                "      com.albandrieu.nabla.entity-ref: component:default/api\n"
                "    x-nabla:\n      id: legacy-api\n"
                "  ignored:\n    image: example.invalid/ignored\n",
                encoding="utf-8",
            )
            gatus = root / "config" / "monitoring" / "gatus-endpoints.yml"
            gatus.parent.mkdir(parents=True)
            gatus.write_text(
                "endpoints:\n  - name: API\n    extra-labels:\n"
                "      nabla_monitor_id: api-health\n"
                "      nabla_service_id: api\n"
                "  - name: Unknown\n    extra-labels:\n"
                "      nabla_monitor_id: missing-probe\n"
                "      nabla_service_id: missing\n",
                encoding="utf-8",
            )
            result = identity_mapping_projection(entities, [compose], gatus, root)
        binding = {(e["sourceType"], e["sourceId"]): e["entityRef"]
                   for e in result["mappings"]}
        self.assertEqual(
            binding[("compose", "apps/demo/compose.yml#services/api")],
            "component:default/api",
        )
        self.assertEqual(binding[("gatus", "api-health")], "component:default/api")
        self.assertEqual(
            binding[("legacy-service-id", "legacy-api")], "component:default/api"
        )
        self.assertEqual(result["unresolved"][0]["sourceId"], "missing-probe")
        self.assertEqual(result["catalogRevision"], catalog_revision(entities))



if __name__ == "__main__":
    unittest.main()
