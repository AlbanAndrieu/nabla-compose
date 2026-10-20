"""Archive-mode contracts for service-consumer Compose discovery."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "nabla_ops" / "compose_paths.py"
CONSUMER = ROOT / "scripts" / "generate-service-consumers.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPOSE_PATHS = load_module("compose_paths_contract", HELPER)


class ServiceConsumerArchiveContractTests(unittest.TestCase):
    def test_archive_discovers_root_and_app_compose_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = (
                root / "docker-compose-truenas.yml",
                root / "compose.ai.yml",
                root / "apps" / "demo" / "compose.yml",
                root / "apps" / "demo" / "compose.override.yaml",
            )
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("services: {}\n", encoding="utf-8")
            unrelated = root / "catalog" / "config.yml"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("version: 1\n", encoding="utf-8")

            discovered = {
                path.as_posix()
                for path in COMPOSE_PATHS.tracked_compose_paths(root)
            }

        self.assertEqual(
            discovered,
            {
                "apps/demo/compose.override.yaml",
                "apps/demo/compose.yml",
                "compose.ai.yml",
                "docker-compose-truenas.yml",
            },
        )

    def test_compose_uses_backstage_ref_and_declared_state(self) -> None:
        consumers = load_module("service_consumers_contract", CONSUMER)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            catalog = root / "catalog"
            catalog.mkdir()
            (catalog / "catalog-info.yaml").write_text(textwrap.dedent(
                """
                apiVersion: backstage.io/v1alpha1
                kind: Component
                metadata:
                  name: doco-cd
                  title: Doco-CD
                  tags: [operations]
                  labels:
                    albandrieu.com/operational-state: active
                spec:
                  type: deployment-automation
                  lifecycle: production
                  owner: group:default/nabla-platform
                ---
                apiVersion: backstage.io/v1alpha1
                kind: Component
                metadata:
                  name: future
                  title: Future
                  tags: [test]
                  labels:
                    albandrieu.com/operational-state: planned
                spec:
                  type: application
                  lifecycle: experimental
                  owner: group:default/nabla-platform
                """).lstrip(), encoding="utf-8")
            (root / "docker-compose-truenas.yml").write_text(textwrap.dedent(
                """
                services:
                  doco-cd:
                    labels:
                      com.albandrieu.nabla.entity-ref: component:default/doco-cd
                    ports: ["9120:9120"]
                  future:
                    labels:
                      com.albandrieu.nabla.entity-ref: component:default/future
                    ports: ["9999:9999"]
                  implicit-duplicate:
                    ports: ["8080:8080"]
                """).lstrip(), encoding="utf-8")
            with patch.object(consumers, "ROOT", root):
                apps, monitors = consumers.collect_services({
                    "defaults": {"host": "172.17.0.24", "interval": "60s"}
                })

        apps_by_id = {item["id"]: item for item in apps}
        monitors_by_id = {item["id"]: item for item in monitors}
        self.assertEqual(set(apps_by_id), {"doco-cd", "future"})
        self.assertEqual(set(monitors_by_id), {"doco-cd"})
        self.assertEqual(monitors_by_id["doco-cd"]["service_id"], "doco-cd")
        self.assertEqual(monitors_by_id["doco-cd"]["port"], 9120)


if __name__ == "__main__":
    unittest.main()
