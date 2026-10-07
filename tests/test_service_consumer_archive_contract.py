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
CONSUMERS = load_module("service_consumers_contract", CONSUMER)


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

    def test_root_compose_requires_explicit_metadata_and_respects_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose-truenas.yml").write_text(
                textwrap.dedent(
                    """
                    services:
                      doco-cd:
                        x-nabla:
                          id: doco-cd
                          name: Doco-CD
                          kind: deployment-automation
                          category: operations
                          monitoring:
                            type: port
                            host: 172.17.0.24
                            port: 9120
                        ports:
                          - "30080:80"
                          - "9120:9120"
                      future:
                        x-nabla:
                          id: future
                          name: Future
                          kind: application
                          category: test
                          status: planned
                          monitoring:
                            type: port
                            host: 172.17.0.24
                            port: 9999
                      implicit-duplicate:
                        ports:
                          - "8080:8080"
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            static = {
                "defaults": {"host": "172.17.0.24", "interval": "60s"},
            }
            with patch.object(CONSUMERS, "ROOT", root):
                apps, monitors = CONSUMERS.collect_services(static)

        apps_by_id = {item["id"]: item for item in apps}
        monitors_by_id = {item["id"]: item for item in monitors}
        self.assertEqual(set(apps_by_id), {"doco-cd", "future"})
        self.assertEqual(set(monitors_by_id), {"doco-cd"})
        self.assertEqual(
            monitors_by_id["doco-cd"],
            {
                "id": "doco-cd",
                "name": "Doco-CD",
                "group": "operations",
                "interval": "60s",
                "type": "port",
                "host": "172.17.0.24",
                "port": 9120,
                "service_id": "doco-cd",
            },
        )


if __name__ == "__main__":
    unittest.main()
