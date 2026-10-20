"""AutoKuma 2.0 static files are one object per stable monitor ID."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/render-autokuma-monitors.py"
SPEC = importlib.util.spec_from_file_location("render_autokuma", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class AutoKumaMaterializationTests(unittest.TestCase):
    def test_repo_manifest_stable_native_files(self) -> None:
        src = ROOT / "apps/autokuma/static/generated-monitors.json"
        defs = renderer.native_definitions(src)
        self.assertGreater(len(defs), 0)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "monitors"
            renderer.apply(defs, dest)
            files = sorted(dest.glob("*.json"))
            self.assertEqual(len(files), len(defs))
            for file in files:
                self.assertTrue(file.name.startswith("nabla-"))
                content = json.loads(file.read_text(encoding="utf-8"))
                self.assertIsInstance(content, dict)
                self.assertNotIn("id", content)
                self.assertIn(content["type"], {"http", "port", "ping"})
            self.assertEqual(
                json.loads((dest / "nabla-ntopng.json").read_text())["name"],
                "ntopng",
            )

    def test_duplicate_ids_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "monitors.json"
            file.write_text(json.dumps([
                {"id": "same", "name": "A", "type": "http", "url": "http://example.test"},
                {"id": "same", "name": "B", "type": "port", "hostname": "test", "port": 80},
            ]))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                renderer.native_definitions(file)

    def test_prunes_only_own_stale_files_and_rejects_unmanaged_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "nabla-stale.json").write_text("{}")
            renderer.apply({"one": '{"type":"ping","name":"One","hostname":"test"}\n'}, folder)
            self.assertFalse((folder / "nabla-stale.json").exists())
            self.assertTrue((folder / "nabla-one.json").exists())
            (folder / "external.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "unmanaged JSON"):
                renderer.apply({"one": '{"type":"ping","name":"One"}\n'}, folder)

    def test_runtime_mount_never_exposes_aggregate(self) -> None:
        compose = (ROOT / "apps/autokuma/compose.yml").read_text(encoding="utf-8")
        self.assertIn("/mnt/cpool/autokuma/static-monitors:/config/static:ro", compose)
        self.assertNotIn("./static:/config/static:ro", compose)
        self.assertIn("AUTOKUMA__DOCKER__ENABLED: \"false\"", compose)


if __name__ == "__main__":
    unittest.main()
