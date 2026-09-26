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


if __name__ == "__main__":
    unittest.main()
