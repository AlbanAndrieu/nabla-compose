"""Offline tests for canonical Backstage catalog and optional website icon parity."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/quality/check-site-catalog-convergence.py"
SPEC = importlib.util.spec_from_file_location("catalog_convergence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixtures(root: Path):
    catalog = root / "catalog"
    (catalog / "generated").mkdir(parents=True)
    entities = [
        {"apiVersion": "backstage.io/v1alpha1", "kind": "Component",
         "entityRef": "component:default/gatus", "metadata": {"name": "gatus"}, "spec": {}},
        {"apiVersion": "backstage.io/v1alpha1", "kind": "Resource",
         "entityRef": "resource:default/postgres-reader", "metadata": {"name": "postgres-reader"}, "spec": {}},
    ]
    def write(entities):
        ordered = sorted(entities, key=lambda item: item["entityRef"])
        digest = hashlib.sha256(json.dumps(ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        (catalog / "generated/entities.json").write_text(json.dumps({
            "model": "backstage", "schemaVersion": 2, "catalogRevision": "sha256:" + digest,
            "entities": entities,
        }), encoding="utf-8")
    write(entities)
    mapping = {"gatus": "gatus.png", "postgres": "postgres.svg"}
    (catalog / "service-icons.json").write_text(json.dumps({
        "version": 1, "icons": {}, "webAssets": mapping,
    }), encoding="utf-8")
    return entities, mapping, write


class CatalogConvergenceTests(unittest.TestCase):
    def test_good_canonical_and_parent_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures(root)
            self.assertEqual(MODULE.audit(root), ([], {
                "entities": 2, "services": 2, "icons": 2,
                "missing_icons": 0, "duplicate_names": 0,
            }))
            self.assertEqual(MODULE.main(["--root", str(root)]), 0)

    def test_missing_icon_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures(root)
            source = root / "catalog/service-icons.json"
            doc = json.loads(source.read_text())
            del doc["webAssets"]["gatus"]
            source.write_text(json.dumps(doc))
            self.assertTrue(any("unmapped" in issue for issue in MODULE.audit(root)[0]))

    def test_wrong_source_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures(root)
            source = root / "catalog/generated/entities.json"
            doc = json.loads(source.read_text())
            doc["catalogRevision"] = "sha256:" + "f" * 64
            source.write_text(json.dumps(doc))
            self.assertTrue(any("catalogRevision" in issue for issue in MODULE.audit(root)[0]))

    def test_duplicate_entity_ref_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entities, _, write = fixtures(root)
            write(entities + [entities[0]])
            self.assertTrue(any("duplicate" in issue for issue in MODULE.audit(root)[0]))

    def test_generated_site_icon_map_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, mapping, _ = fixtures(root)
            site = root / "site-icons.ts"
            site.write_text(MODULE.TS_EXPORT + json.dumps(mapping) + ";\n")
            self.assertEqual(MODULE.audit(root, site)[0], [])
            site.write_text(MODULE.TS_EXPORT + '{"gatus":"wrong.svg"};\n')
            self.assertTrue(any("differs" in issue for issue in MODULE.audit(root, site)[0]))

    def test_inconsistent_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entities, _, write = fixtures(root)
            entities[0]["metadata"]["name"] = "another-id"
            write(entities)
            self.assertTrue(any("inconsistent" in issue for issue in MODULE.audit(root)[0]))

    def test_rejects_filename_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures(root)
            path = root / "catalog/service-icons.json"
            doc = json.loads(path.read_text())
            doc["webAssets"]["gatus"] = "../private.key"
            path.write_text(json.dumps(doc))
            self.assertTrue(any("unsafe icon" in issue for issue in MODULE.audit(root)[0]))

    def test_validation_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures(root)
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            MODULE.audit(root)
            after = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
