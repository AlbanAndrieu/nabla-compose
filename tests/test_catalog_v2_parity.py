from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.catalog_v2 import (  # noqa: E402
    FIELD_DISPOSITIONS,
    backstage_entity_ref,
    backstage_graph_errors,
    backstage_materialization_debt,
    backstage_runtime_binding_errors,
    build_parity_report,
    compatibility_relation_debt,
    desired_exposure_errors,
    preparation_errors,
)


class CatalogV2ParityTests(unittest.TestCase):
    def test_backstage_descriptor_validation_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "apiVersion"):
            backstage_entity_ref(
                {
                    "kind": "Resource",
                    "metadata": {"name": "database"},
                    "spec": {"type": "database", "owner": "group:default/team"},
                }
            )

        with self.assertRaisesRegex(ValueError, "spec.owner is required"):
            backstage_entity_ref(
                {
                    "apiVersion": "backstage.io/v1alpha1",
                    "kind": "Resource",
                    "metadata": {"name": "database"},
                    "spec": {
                        "type": "database",
                    },
                }
            )

        with self.assertRaisesRegex(ValueError, "spec.children must be a list"):
            backstage_entity_ref(
                {
                    "apiVersion": "backstage.io/v1alpha1",
                    "kind": "Group",
                    "metadata": {"name": "team"},
                    "spec": {"type": "team", "children": "none"},
                }
            )

    def test_materialized_service_requires_matching_runtime_entity_ref(self) -> None:
        generated = {
            "services": [
                {
                    "id": "example",
                    "name": "Example",
                    "kind": "service",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "example",
                }
            ]
        }
        entities = [
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Component",
                "metadata": {"name": "example"},
                "spec": {
                    "type": "service",
                    "lifecycle": "production",
                    "owner": "group:default/nabla-platform",
                },
            }
        ]

        self.assertEqual(
            backstage_runtime_binding_errors(generated, entities, []),
            [
                "apps/example/compose.yml:example: materialized "
                "component:default/example requires "
                "com.albandrieu.nabla.entity-ref"
            ],
        )

        self.assertEqual(
            backstage_runtime_binding_errors(
                generated,
                entities,
                [
                    {
                        "sourcePath": "apps/example/compose.yml",
                        "composeService": "example",
                        "entityRef": "component:default/missing",
                    }
                ],
            ),
            [
                "apps/example/compose.yml:example: entity-ref label "
                "component:default/missing does not match materialized "
                "component:default/example",
                "apps/example/compose.yml:example: entity-ref label references "
                "unknown Backstage entity: component:default/missing",
            ],
        )

        self.assertEqual(
            backstage_runtime_binding_errors(
                generated,
                entities,
                [
                    {
                        "sourcePath": "apps/example/compose.yml",
                        "composeService": "example",
                        "entityRef": "component:default/example",
                    }
                ],
            ),
            [],
        )

    def test_backstage_materialization_debt_tracks_missing_descriptors(self) -> None:
        generated = {
            "services": [
                {
                    "id": "materialized",
                    "name": "Materialized",
                    "kind": "service",
                    "sourcePath": "apps/materialized/compose.yml",
                    "composeService": "materialized",
                },
                {
                    "id": "missing",
                    "name": "Missing",
                    "kind": "service",
                    "sourcePath": "apps/missing/compose.yml",
                    "composeService": "missing",
                },
            ]
        }
        entities = [
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Component",
                "metadata": {"name": "materialized"},
                "spec": {
                    "type": "service",
                    "lifecycle": "production",
                    "owner": "group:default/nabla-platform",
                },
            }
        ]

        self.assertEqual(
            backstage_materialization_debt(generated, entities),
            [
                {
                    "serviceId": "missing",
                    "sourcePath": "apps/missing/compose.yml",
                    "composeService": "missing",
                    "candidateEntityRef": "component:default/missing",
                    "expectedCatalogInfoPath": "apps/missing/catalog-info.yaml",
                    "operationalState": "active",
                    "operationalCriticality": None,
                    "legacyKind": "service",
                    "reason": "missing-backstage-entity",
                    "matchingEntityRefs": [],
                }
            ],
        )

    def test_backstage_graph_requires_full_resolved_refs(self) -> None:
        entities = [
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Group",
                "metadata": {"name": "team"},
                "spec": {"type": "team", "children": []},
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "System",
                "metadata": {"name": "system"},
                "spec": {"owner": "group:default/team"},
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Component",
                "metadata": {"name": "service"},
                "spec": {
                    "type": "service",
                    "lifecycle": "production",
                    "owner": "group:default/team",
                    "system": "system:default/system",
                    "dependsOn": ["resource:default/missing"],
                },
            },
        ]
        self.assertEqual(
            backstage_graph_errors(entities),
            [
                "component:default/service: spec.dependsOn references unknown entity:"
                " resource:default/missing"
            ],
        )

        entities[2]["spec"]["owner"] = "team"
        self.assertIn(
            "component:default/service: spec.owner must use a full Backstage entity ref:"
            " team",
            backstage_graph_errors(entities),
        )

    def test_desired_public_exposure_requires_resolved_gateway_named_port_and_access(self) -> None:
        entities = [
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Group",
                "metadata": {"name": "team"},
                "spec": {"type": "team", "children": []},
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Resource",
                "metadata": {"name": "edge"},
                "spec": {
                    "type": "network-edge",
                    "owner": "group:default/team",
                },
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Component",
                "metadata": {"name": "service"},
                "spec": {
                    "type": "service",
                    "lifecycle": "production",
                    "owner": "group:default/team",
                },
            },
        ]
        binding = {
            "sourcePath": "apps/service/compose.yml",
            "composeService": "service",
            "entityRef": "component:default/service",
            "namedPorts": ["web"],
            "exposure": [
                {
                    "name": "public",
                    "hostnames": ["service.example.test"],
                    "protocol": "HTTPS",
                    "visibility": "public",
                    "gatewayRef": "resource:default/edge",
                    "backendPort": "web",
                    "access": {"required": True},
                }
            ],
        }

        self.assertEqual(desired_exposure_errors(entities, [binding]), [])

        invalid = {
            **binding,
            "exposure": [
                {
                    "name": "public",
                    "hostnames": [],
                    "protocol": "HTTPS",
                    "visibility": "public",
                    "gatewayRef": "resource:default/missing",
                    "backendPort": "missing",
                    "access": {},
                }
            ],
        }
        errors = desired_exposure_errors(entities, [invalid])
        self.assertIn(
            "apps/service/compose.yml:service:exposure[0]: public exposure "
            "requires explicit hostnames",
            errors,
        )
        self.assertIn(
            "apps/service/compose.yml:service:exposure[0]: gatewayRef references "
            "unknown entity: resource:default/missing",
            errors,
        )
        self.assertIn(
            "apps/service/compose.yml:service:exposure[0]: backendPort must "
            "reference a named Compose port: missing",
            errors,
        )
        self.assertIn(
            "apps/service/compose.yml:service:exposure[0]: public exposure "
            "requires explicit access.required boolean",
            errors,
        )

    def test_relation_duplication_is_reported_as_transition_debt(self) -> None:
        entities = [
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Group",
                "metadata": {"name": "team"},
                "spec": {"type": "team", "children": []},
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Resource",
                "metadata": {"name": "database"},
                "spec": {
                    "type": "database",
                    "owner": "group:default/team",
                },
            },
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Component",
                "metadata": {"name": "worker"},
                "spec": {
                    "type": "worker",
                    "lifecycle": "production",
                    "owner": "group:default/team",
                    "dependsOn": ["resource:default/database"],
                },
            },
        ]
        debt = compatibility_relation_debt(
            entities,
            [
                {
                    "sourcePath": "apps/worker/compose.yml",
                    "composeService": "worker",
                    "entityRef": "component:default/worker",
                    "relations": [
                        {
                            "target": "database",
                            "type": "storesIn",
                        }
                    ],
                }
            ],
        )
        self.assertEqual(
            debt,
            [
                {
                    "source": "component:default/worker",
                    "target": "resource:default/database",
                    "backstageType": "dependsOn",
                    "legacyType": "storesIn",
                    "sourcePath": "apps/worker/compose.yml",
                    "composeService": "worker",
                }
            ],
        )

    def test_explicit_id_maps_to_stable_resource_ref(self) -> None:
        report = build_parity_report(
            {
                "services": [
                    {
                        "id": "postgresql",
                        "name": "PostgreSQL",
                        "tunnelUrl": "postgres://postgres.albandrieu.com:5432/",
                        "external": False,
                    }
                ]
            },
            {"services": []},
            {
                "services": [
                    {
                        "id": "postgresql",
                        "name": "PostgreSQL",
                        "kind": "database",
                    }
                ]
            },
            [
                {
                    "apiVersion": "backstage.io/v1alpha1",
                    "kind": "Resource",
                    "metadata": {"name": "postgresql"},
                    "spec": {
                        "type": "database",
                        "owner": "group:default/nabla-platform",
                    },
                }
            ],
        )

        entry = report["entries"][0]
        self.assertEqual(entry["matchStrategy"], "explicit-id")
        self.assertFalse(entry["identityDebt"])
        self.assertTrue(entry["identityReady"])
        self.assertTrue(entry["backstageMaterialized"])
        self.assertEqual(entry["entityRef"], "resource:default/postgresql")
        self.assertEqual(entry["backstageEntityRef"], "resource:default/postgresql")
        self.assertEqual(entry["candidateEntityRef"], "resource:default/postgresql")
        self.assertIn("resource:default/postgresql", report["byEntityRef"])

    def test_legacy_slug_match_is_visible_identity_debt(self) -> None:
        report = build_parity_report(
            {"services": [{"name": "FastAPI Sample"}]},
            {"services": []},
            {
                "services": [
                    {
                        "id": "fastapi-sample",
                        "name": "FastAPI Sample service",
                        "kind": "api",
                    }
                ]
            },
        )

        entry = report["entries"][0]
        self.assertEqual(entry["matchStrategy"], "legacy-slug")
        self.assertTrue(entry["identityDebt"])
        self.assertEqual(entry["candidateEntityRef"], "component:default/fastapi-sample")
        self.assertEqual(preparation_errors(report), [])

    def test_static_legacy_id_can_be_ready_without_generated_service(self) -> None:
        report = build_parity_report(
            {"services": [{"id": "postgresql", "name": "PostgreSQL"}]},
            {"services": []},
            {"services": []},
            [
                {
                    "apiVersion": "backstage.io/v1alpha1",
                    "kind": "Resource",
                    "metadata": {"name": "postgresql"},
                    "spec": {
                        "type": "database",
                        "owner": "group:default/nabla-platform",
                    },
                }
            ],
        )

        entry = report["entries"][0]
        self.assertEqual(entry["matchStrategy"], "unmapped")
        self.assertEqual(entry["backstageMatchStrategy"], "explicit-id")
        self.assertTrue(entry["identityReady"])
        self.assertFalse(entry["identityDebt"])
        self.assertEqual(entry["backstageEntityRef"], "resource:default/postgresql")

    def test_materialized_backstage_ref_wins_over_legacy_kind_inference(self) -> None:
        report = build_parity_report(
            {
                "services": [
                    {
                        "id": "postgresql",
                        "name": "PostgreSQL",
                    }
                ]
            },
            {"services": []},
            {
                "services": [
                    {
                        "id": "postgresql",
                        "name": "PostgreSQL",
                        "kind": "native-truenas-database",
                    }
                ]
            },
            [
                {
                    "apiVersion": "backstage.io/v1alpha1",
                    "kind": "Resource",
                    "metadata": {"name": "postgresql"},
                    "spec": {
                        "type": "database",
                        "owner": "group:default/nabla-platform",
                    },
                }
            ],
        )

        entry = report["entries"][0]
        self.assertEqual(entry["backstageEntityRef"], "resource:default/postgresql")
        self.assertEqual(entry["candidateEntityRef"], "resource:default/postgresql")

    def test_override_preserves_desired_access_intent_independently_of_status(self) -> None:
        report = build_parity_report(
            {
                "services": [
                    {
                        "id": "sample",
                        "name": "Sample",
                        "tunnelUrl": "https://sample.albandrieu.com",
                        "external": True,
                    }
                ]
            },
            {
                "services": [
                    {
                        "name": "Sample",
                        "cloudflareAccessRequired": True,
                        "securityException": "reviewed exception",
                    }
                ]
            },
            {"services": [{"id": "sample", "name": "Sample", "kind": "api"}]},
        )

        exposure = report["entries"][0]["desiredExposure"]
        self.assertEqual(exposure["hostname"], "sample.albandrieu.com")
        self.assertTrue(exposure["legacyExternal"])
        self.assertTrue(exposure["accessRequired"])
        self.assertEqual(exposure["securityException"], "reviewed exception")
        self.assertEqual(report["summary"]["accessRequiredEntries"], 1)
        self.assertEqual(report["summary"]["securityExceptionEntries"], 1)

    def test_duplicate_generated_catalog_id_is_a_hard_preparation_error(self) -> None:
        report = build_parity_report(
            {"services": [{"id": "example", "name": "Example"}]},
            {"services": []},
            {
                "services": [
                    {"id": "example", "name": "Example A", "kind": "service"},
                    {"id": "example", "name": "Example B", "kind": "service"},
                ]
            },
        )

        self.assertIn(
            "duplicate generated catalog id: example",
            preparation_errors(report),
        )

    def test_duplicate_legacy_name_is_a_hard_preparation_error(self) -> None:
        report = build_parity_report(
            {
                "services": [
                    {"name": "Example"},
                    {"name": "Example"},
                ]
            },
            {"services": []},
            {"services": []},
        )

        self.assertIn(
            "duplicate legacy service name: Example",
            preparation_errors(report),
        )

    def test_unknown_legacy_field_is_a_hard_preparation_error(self) -> None:
        report = build_parity_report(
            {"services": [{"name": "Example", "mystery": True}]},
            {"services": []},
            {"services": []},
        )

        self.assertEqual(
            preparation_errors(report),
            ["legacy field has no v2 disposition: mystery"],
        )
        self.assertEqual(
            report["entries"][0]["fieldDispositions"]["mystery"],
            "UNRESOLVED",
        )

    def test_orphan_override_is_a_hard_preparation_error(self) -> None:
        report = build_parity_report(
            {"services": [{"name": "Example"}]},
            {"services": [{"name": "Missing", "external": True}]},
            {"services": []},
        )
        self.assertEqual(
            preparation_errors(report),
            ["override target not found in base catalog: Missing"],
        )

    def test_repository_legacy_fields_all_have_explicit_dispositions(self) -> None:
        paths = (
            ROOT / "catalog" / "homelab-services.json",
            ROOT / "catalog" / "homelab-exposure-overrides.json",
        )
        actual_fields: set[str] = set()
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for service in payload["services"]:
                actual_fields.update(service)

        self.assertEqual(actual_fields - FIELD_DISPOSITIONS.keys(), set())

    def test_repository_preparation_inventory_has_no_hidden_field_or_override(self) -> None:
        backstage_entities: list[dict] = []
        for path in [
            ROOT / "catalog" / "catalog-info.yaml",
            *sorted((ROOT / "apps").glob("*/catalog-info.yaml")),
        ]:
            if not path.exists():
                continue
            backstage_entities.extend(
                item
                for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
                if isinstance(item, dict)
            )

        report = build_parity_report(
            json.loads(
                (ROOT / "catalog" / "homelab-services.json").read_text(
                    encoding="utf-8"
                )
            ),
            json.loads(
                (ROOT / "catalog" / "homelab-exposure-overrides.json").read_text(
                    encoding="utf-8"
                )
            ),
            json.loads(
                (ROOT / "catalog" / "services.json").read_text(encoding="utf-8")
            ),
            backstage_entities,
        )

        self.assertEqual(preparation_errors(report), [])
        self.assertEqual(backstage_graph_errors(backstage_entities), [])
        self.assertEqual(
            report["summary"]["legacyServices"],
            len(report["entries"]),
        )
        self.assertGreater(report["summary"]["identityDebt"], 0)
        self.assertGreater(report["summary"]["backstageEntities"], 0)
        self.assertEqual(
            report["summary"]["backstageMaterializationDebt"],
            len(report["backstageMaterializationDebt"]),
        )
        self.assertGreater(
            report["summary"]["backstageMaterializationDebtByState"].get(
                "active",
                0,
            ),
            0,
        )
        self.assertGreater(report["summary"]["backstageMaterializedEntries"], 0)
        self.assertEqual(
            report["summary"]["resolvedEntityRefs"],
            len(report["byEntityRef"]),
        )
        self.assertGreater(report["summary"]["resolvedEntityRefs"], 0)
        self.assertGreater(report["summary"]["identityReadyEntries"], 0)
        self.assertGreater(report["summary"]["desiredExposureEntries"], 0)

        entries_by_name = {entry["name"]: entry for entry in report["entries"]}
        for name, entity_ref in {
            "TrueNAS": "resource:default/truenas",
            "pfSense": "resource:default/pfsense",
            "PostgreSQL": "resource:default/postgresql",
        }.items():
            with self.subTest(name=name):
                entry = entries_by_name[name]
                self.assertTrue(entry["identityReady"])
                self.assertFalse(entry["identityDebt"])
                self.assertEqual(entry["backstageEntityRef"], entity_ref)

        home = entries_by_name["Home"]
        self.assertTrue(home["identityDebt"])
        self.assertIsNone(home["backstageEntityRef"])
        self.assertFalse(report["cutoverReady"])


if __name__ == "__main__":
    unittest.main()
