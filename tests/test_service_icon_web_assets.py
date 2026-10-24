"""Contract for the one authored web icon mapping in the Nabla catalog.

The website vendors the images; this catalog owns the service -> filename identity.
A new Backstage Component must not silently render a generic icon.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ICON_FILE = re.compile(r"[A-Za-z0-9._-]+\.(?:svg|png|jpg)\Z")


class ServiceIconWebAssetsContract(unittest.TestCase):
    def test_web_assets_cover_declared_components_and_legacy_services(self) -> None:
        icons = json.loads((ROOT / "catalog/service-icons.json").read_text(encoding="utf-8"))
        self.assertEqual(icons["version"], 1)
        self.assertIsInstance(icons["icons"], dict)  # Historical graph emoji interface.
        mapping = icons["webAssets"]
        self.assertIsInstance(mapping, dict)
        self.assertGreater(len(mapping), 0)
        for name, filename in mapping.items():
            with self.subTest(name=name):
                self.assertRegex(name, ID)
                self.assertRegex(filename, ICON_FILE)
                self.assertNotIn("..", filename)
                self.assertNotIn("/", filename)
        entities = json.loads(
            (ROOT / "catalog/generated/entities.json").read_text(encoding="utf-8")
        )["entities"]
        legacy = json.loads(
            (ROOT / "catalog/homelab-services.json").read_text(encoding="utf-8")
        )["services"]
        names = {item["metadata"]["name"] for item in entities if item["kind"] == "Component"}
        names.update(item["id"] for item in legacy)
        missing = sorted(
            name for name in names
            if name not in mapping and not any(name.startswith(parent + "-") for parent in mapping)
        )
        self.assertEqual(missing, [], "Add a specific webAssets filename for each new service")


if __name__ == "__main__":
    unittest.main()
