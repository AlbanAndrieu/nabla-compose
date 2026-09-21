from __future__ import annotations

from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.business_criticality import (  # noqa: E402
    business_continuity_errors,
    business_criticality,
    business_criticality_inventory,
    parse_iso8601_duration,
)


def _policy() -> dict:
    payload = yaml.safe_load(
        (ROOT / "catalog" / "business-criticality-policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(payload, dict):
        raise AssertionError("business criticality policy must be a mapping")
    return payload


def _entity(
    *,
    declared: str = "high",
    mtpd: str = "P1D",
    rto: str = "PT4H",
    rpo: str = "PT1H",
    impact: str = "medium",
) -> dict:
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": "example",
            "labels": {
                "albandrieu.com/operational-criticality": "medium",
                "albandrieu.com/business-criticality": declared,
            },
            "annotations": {
                "albandrieu.com/bia-mtpd": mtpd,
                "albandrieu.com/bia-rto": rto,
                "albandrieu.com/bia-rpo": rpo,
                "albandrieu.com/bia-mbco": "minimum-service",
                "albandrieu.com/bia-status": "provisional",
                "albandrieu.com/bia-reviewed-at": "2026-09-21",
                "albandrieu.com/bia-impact-operational": impact,
            },
        },
        "spec": {
            "type": "service",
            "lifecycle": "production",
            "owner": "group:default/nabla-platform",
        },
    }


def _repository_entities() -> list[dict]:
    paths = [ROOT / "catalog" / "catalog-info.yaml"]
    paths.extend(sorted((ROOT / "apps").glob("*/catalog-info.yaml")))
    entities: list[dict] = []
    for path in paths:
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if isinstance(document, dict):
                entities.append(document)
    return entities


class BusinessCriticalityTests(unittest.TestCase):
    def test_iso_duration_parser_supports_bia_policy_values(self) -> None:
        self.assertEqual(parse_iso8601_duration("PT15M"), 900)
        self.assertEqual(parse_iso8601_duration("PT4H"), 14400)
        self.assertEqual(parse_iso8601_duration("P3D"), 259200)

    def test_business_criticality_uses_strictest_driver(self) -> None:
        result = business_criticality(
            _entity(
                declared="critical",
                mtpd="P1D",
                rto="PT4H",
                rpo="PT1H",
                impact="critical",
            ),
            _policy(),
        )
        assert result is not None
        self.assertEqual(result["calculated"], "critical")
        self.assertEqual(result["recoveryMarginSeconds"], 72000)
        self.assertIn(
            {
                "driver": "impact:operational",
                "level": "critical",
                "value": "critical",
            },
            result["drivers"],
        )

    def test_rto_must_be_lower_than_mtpd(self) -> None:
        errors = business_continuity_errors(
            [_entity(declared="critical", mtpd="PT4H", rto="PT4H")],
            _policy(),
        )
        self.assertEqual(
            errors,
            [
                "component:default/example: RTO must be lower than MTPD/DMTP",
            ],
        )

    def test_declared_business_criticality_must_match_calculation(self) -> None:
        errors = business_continuity_errors(
            [_entity(declared="low", mtpd="P1D", rto="PT4H", rpo="PT1H")],
            _policy(),
        )
        self.assertEqual(
            errors,
            [
                "component:default/example: business-criticality=low does not match "
                "calculated=high"
            ],
        )

    def test_repository_bia_profiles_are_consistent(self) -> None:
        entities = _repository_entities()
        policy = _policy()
        self.assertEqual(business_continuity_errors(entities, policy), [])

        inventory = business_criticality_inventory(entities, policy)
        self.assertGreaterEqual(len(inventory), 12)
        self.assertTrue(
            all(item["declared"] == item["calculated"] for item in inventory)
        )
        self.assertTrue(
            all(item["status"] == "provisional" for item in inventory)
        )

        by_ref = {item["entityRef"]: item for item in inventory}
        self.assertEqual(
            by_ref["resource:default/truenas"]["calculated"],
            "critical",
        )
        self.assertEqual(
            by_ref["resource:default/kubernetes"]["calculated"],
            "medium",
        )
        self.assertEqual(
            by_ref["component:default/cartography"]["calculated"],
            "low",
        )


if __name__ == "__main__":
    unittest.main()
