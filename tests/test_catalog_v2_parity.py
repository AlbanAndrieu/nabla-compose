from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.catalog_v2 import (  # noqa: E402
    FIELD_DISPOSITIONS,
    build_parity_report,
    preparation_errors,
)


class CatalogV2ParityTests(unittest.TestCase):
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
        )

        entry = report["entries"][0]
        self.assertEqual(entry["matchStrategy"], "explicit-id")
        self.assertFalse(entry["identityDebt"])
        self.assertEqual(entry["candidateEntityRef"], "resource:default/postgresql")
        self.assertEqual(entry["entityRef"], "resource:default/postgresql")
        self.assertIn(
            "resource:default/postgresql",
            report["byEntityRef"],
        )

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
        )

        self.assertEqual(preparation_errors(report), [])
        self.assertEqual(
            report["summary"]["legacyServices"],
            len(report["entries"]),
        )
        self.assertGreater(report["summary"]["identityDebt"], 0)
        self.assertGreater(report["summary"]["desiredExposureEntries"], 0)
        self.assertEqual(
            report["summary"]["resolvedEntityRefs"],
            len(report["byEntityRef"]),
        )
        self.assertFalse(report["cutoverReady"])


if __name__ == "__main__":
    unittest.main()
