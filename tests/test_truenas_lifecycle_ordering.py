from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "scripts/truenas/plan-app-lifecycle-order.py"
REBOOT = ROOT / "scripts/truenas/reboot-homelab.sh"
MATERIALIZE = ROOT / "scripts/truenas/materialize-reboot-bundle.sh"


class TrueNASLifecycleOrderingTests(unittest.TestCase):
    def run_planner(
        self,
        apps: list[dict[str, str]],
        services: list[dict[str, object]],
        relations: list[dict[str, str]],
        topology_nodes: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps.json").write_text(json.dumps(apps), encoding="utf-8")
            (root / "services.json").write_text(
                json.dumps({"services": services}), encoding="utf-8"
            )
            (root / "topology.json").write_text(
                json.dumps(
                    {
                        "nodes": topology_nodes or [],
                        "relations": relations,
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(PLANNER),
                    "--apps",
                    str(root / "apps.json"),
                    "--services",
                    str(root / "services.json"),
                    "--topology",
                    str(root / "topology.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_foundation_data_and_dependents_start_in_safe_order(self) -> None:
        app_ids = [
            "pihole",
            "adguard-home",
            "traefik",
            "docker-socket-proxy",
            "vaultwarden",
            "postgres",
            "mongo",
            "clickhouse",
            "opensearch",
            "graylog",
            "n8n",
            "code",
        ]
        apps = [{"id": app, "state": "RUNNING"} for app in app_ids]
        services = [
            self.service(
                "pihole",
                "dns",
                "network",
                "apps/pihole/compose.yml",
                lifecycle=("foundation", 10),
            ),
            self.service(
                "traefik",
                "edge",
                "network",
                "apps/traefik/compose.yml",
                lifecycle=("foundation", 10),
            ),
            self.service(
                "docker-socket-proxy",
                "security-proxy",
                "infrastructure",
                "docker-compose.yml",
                lifecycle=("bootstrap-runtime", 0),
            ),
            self.service(
                "vaultwarden",
                "password-manager",
                "security",
                "apps/vaultwarden/compose.yml",
                lifecycle=("foundation", 10),
            ),
            self.service(
                "mongo",
                "database",
                "data",
                "apps/mongo/compose.yml",
                lifecycle=("primary-data", 20),
            ),
            self.service(
                "clickhouse",
                "database",
                "data",
                "apps/clickhouse/compose.yml",
                lifecycle=("secondary-data", 30),
            ),
            self.service(
                "opensearch-security",
                "search",
                "security",
                "apps/opensearch/compose.yml",
                lifecycle=("secondary-data", 30),
            ),
            self.service(
                "graylog",
                "log-management",
                "observability",
                "apps/graylog/compose.yml",
                lifecycle=("platform-services", 40),
            ),
            self.service(
                "n8n",
                "workflow",
                "automation",
                "apps/n8n/compose.yml",
            ),
            self.service(
                "code-server",
                "development-environment",
                "development",
                "apps/code/compose.yml",
            ),
        ]
        topology_nodes = [
            self.runtime_node(
                "adguard-home",
                "adguard-home",
                "dns-filter",
                "network",
                lifecycle=("foundation", 10),
            ),
            self.runtime_node(
                "postgresql",
                "postgres",
                "database",
                "data",
                lifecycle=("primary-data", 20),
            ),
        ]
        relations = [
            self.relation("graylog", "mongo", "dependsOn"),
            self.relation("graylog", "opensearch-security", "storesIn"),
            self.relation("n8n", "postgresql", "dependsOn"),
        ]

        plan = self.run_planner(apps, services, relations, topology_nodes)
        start = plan["start_order"]
        stop = plan["stop_order"]

        foundation_after_proxy = [
            "pihole",
            "adguard-home",
            "traefik",
            "vaultwarden",
        ]
        for foundation in foundation_after_proxy:
            self.assertLess(
                start.index("docker-socket-proxy"),
                start.index(foundation),
            )

        primary_data = ["postgres", "mongo"]
        secondary_data = ["clickhouse", "opensearch"]
        for foundation in foundation_after_proxy:
            for database in primary_data:
                self.assertLess(start.index(foundation), start.index(database))
        for database in primary_data:
            for engine in secondary_data:
                self.assertLess(start.index(database), start.index(engine))

        self.assertLess(start.index("mongo"), start.index("graylog"))
        self.assertLess(start.index("opensearch"), start.index("graylog"))
        self.assertLess(start.index("postgres"), start.index("n8n"))
        self.assertEqual(stop, list(reversed(start)))

        for app, expected in {
            "docker-socket-proxy": ("bootstrap-runtime", 0),
            "pihole": ("foundation", 10),
            "adguard-home": ("foundation", 10),
            "postgres": ("primary-data", 20),
            "mongo": ("primary-data", 20),
            "opensearch": ("secondary-data", 30),
        }.items():
            phase, priority = expected
            self.assertEqual(
                plan["lifecycle_phase_by_app"][app],
                {"name": phase, "order": priority, "source": "catalog"},
            )

    def test_declared_lifecycle_overrides_kind_and_category_fallback(self) -> None:
        apps = [
            {"id": "sentry", "state": "RUNNING"},
            {"id": "mongo", "state": "RUNNING"},
        ]
        services = [
            self.service(
                "sentry-web",
                "reverse-proxy",
                "network",
                "apps/sentry/compose.yml",
                lifecycle=("platform-services", 40),
            ),
            self.service(
                "mongo",
                "database",
                "data",
                "apps/mongo/compose.yml",
                lifecycle=("primary-data", 20),
            ),
        ]

        plan = self.run_planner(apps, services, [])

        self.assertLess(
            plan["start_order"].index("mongo"),
            plan["start_order"].index("sentry"),
        )
        self.assertEqual(
            plan["lifecycle_phase_by_app"]["sentry"],
            {"name": "platform-services", "order": 40, "source": "catalog"},
        )

    def test_conflicting_declared_lifecycle_is_rejected(self) -> None:
        apps = [{"id": "opensearch", "state": "RUNNING"}]
        services = [
            self.service(
                "opensearch",
                "search",
                "data",
                "apps/opensearch/compose.yml",
                lifecycle=("secondary-data", 30),
            ),
            self.service(
                "opensearch-security",
                "search",
                "security",
                "apps/opensearch/compose.yml",
                lifecycle=("platform-services", 40),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps.json").write_text(json.dumps(apps), encoding="utf-8")
            (root / "services.json").write_text(
                json.dumps({"services": services}), encoding="utf-8"
            )
            (root / "topology.json").write_text(
                json.dumps({"nodes": [], "relations": []}), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3",
                    str(PLANNER),
                    "--apps",
                    str(root / "apps.json"),
                    "--services",
                    str(root / "services.json"),
                    "--topology",
                    str(root / "topology.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting declared lifecycle", result.stderr)

    def test_source_path_maps_multi_service_app_and_normalized_app_id(self) -> None:
        apps = [
            {"id": "opensearch", "state": "RUNNING"},
            {"id": "elastic-search", "state": "RUNNING"},
            {"id": "graylog", "state": "RUNNING"},
        ]
        services = [
            self.service(
                "opensearch-security",
                "search",
                "security",
                "apps/opensearch/compose.yml",
                lifecycle=("secondary-data", 30),
            ),
            self.service(
                "elasticsearch",
                "search",
                "data",
                "apps/elasticsearch/compose.yml",
            ),
            self.service(
                "graylog",
                "log-management",
                "observability",
                "apps/graylog/compose.yml",
                lifecycle=("platform-services", 40),
            ),
        ]
        relations = [
            self.relation("graylog", "opensearch-security", "storesIn")
        ]

        plan = self.run_planner(apps, services, relations)

        self.assertNotIn("opensearch", plan["unmapped_apps"])
        self.assertNotIn("elastic-search", plan["unmapped_apps"])
        self.assertLess(
            plan["start_order"].index("opensearch"),
            plan["start_order"].index("graylog"),
        )

    def test_runtime_topology_node_maps_app_without_compose_service(self) -> None:
        apps = [
            {"id": "adguard-home", "state": "RUNNING"},
            {"id": "postgres", "state": "RUNNING"},
        ]
        topology_nodes = [
            self.runtime_node(
                "adguard-home",
                "adguard-home",
                "dns-filter",
                "network",
                lifecycle=("foundation", 10),
            ),
            self.runtime_node(
                "postgresql",
                "postgres",
                "database",
                "data",
                lifecycle=("primary-data", 20),
            ),
        ]

        plan = self.run_planner(apps, [], [], topology_nodes)

        self.assertEqual(plan["unmapped_apps"], [])
        self.assertLess(
            plan["start_order"].index("adguard-home"),
            plan["start_order"].index("postgres"),
        )
        self.assertEqual(
            plan["lifecycle_phase_by_app"]["postgres"],
            {"name": "primary-data", "order": 20, "source": "catalog"},
        )

    def test_reboot_resume_repairs_order_without_replacing_manifest(self) -> None:
        script = REBOOT.read_text(encoding="utf-8")

        self.assertIn("build_effective_resume_plan", script)
        self.assertIn("selected App membership changed", script)
        self.assertIn("resume-plan-effective.json", script)
        self.assertIn("original resume-plan.json preserved", script)
        self.assertIn("reconcile-reboot-resume.sh", script)
        self.assertNotIn("Starting saved Apps in topology dependency order", script)

    def test_bundle_requires_phased_planner_and_resume_reconciler(self) -> None:
        script = MATERIALIZE.read_text(encoding="utf-8")

        self.assertIn("start_wave_phases", script)
        self.assertIn("sourcePath", script)
        self.assertIn("build_effective_resume_plan", script)
        self.assertIn("reconcile-reboot-resume.sh", script)

    @staticmethod
    def service(
        service_id: str,
        kind: str,
        category: str,
        source_path: str,
        *,
        lifecycle: tuple[str, int] | None = None,
    ) -> dict:
        service = {
            "id": service_id,
            "kind": kind,
            "category": category,
            "sourcePath": source_path,
            "runtime": {
                "provider": "truenas-app",
                "containerService": service_id,
            },
        }
        if lifecycle is not None:
            phase, priority = lifecycle
            service["lifecycle"] = {"phase": phase, "priority": priority}
        return service

    @staticmethod
    def runtime_node(
        node_id: str,
        app_id: str,
        kind: str,
        category: str,
        *,
        lifecycle: tuple[str, int] | None = None,
    ) -> dict:
        node = {
            "id": node_id,
            "kind": kind,
            "category": category,
            "runtime": {
                "provider": "truenas-app",
                "appId": app_id,
            },
        }
        if lifecycle is not None:
            phase, priority = lifecycle
            node["lifecycle"] = {"phase": phase, "priority": priority}
        return node

    @staticmethod
    def relation(source: str, target: str, relation_type: str) -> dict[str, str]:
        return {
            "source": source,
            "target": target,
            "type": relation_type,
            "strength": "required",
        }


if __name__ == "__main__":
    unittest.main()
