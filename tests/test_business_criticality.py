from __future__ import annotations

from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.business_criticality import (  # noqa: E402
    business_continuity_coverage_errors,
    business_continuity_errors,
    business_criticality,
    business_criticality_inventory,
    effective_dependency_criticality_inventory,
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
                "albandrieu.com/operational-state": "active",
                "albandrieu.com/operational-criticality": "medium",
                "albandrieu.com/business-criticality": declared,
                "albandrieu.com/bia-scope": "direct",
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

    def test_policy_method_is_fail_closed(self) -> None:
        policy = _policy()
        policy["method"] = "weighted-average"

        with self.assertRaisesRegex(
            ValueError,
            "policy method must be max-of-drivers",
        ):
            business_criticality(_entity(), policy)

    def test_policy_thresholds_must_increase_by_tier(self) -> None:
        policy = _policy()
        policy["levels"]["high"]["rtoMax"] = "PT30M"

        with self.assertRaisesRegex(
            ValueError,
            "rto thresholds must increase",
        ):
            business_criticality(_entity(), policy)

    def test_invalid_iso_duration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported ISO-8601 duration"):
            parse_iso8601_duration("P1DT")

    def test_component_requires_operational_state_for_bia_scope(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "missing-state",
                "labels": {},
            },
            "spec": {
                "type": "service",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "component:default/missing-state: Component requires an "
                "operational-state label for BIA coverage"
            ],
        )

    def test_invalid_operational_state_cannot_bypass_bia_coverage(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "bad-state",
                "labels": {
                    "albandrieu.com/operational-state": "acitve",
                },
            },
            "spec": {
                "type": "service",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "component:default/bad-state: operational-state must be one of: "
                "active, disabled, planned"
            ],
        )

    def test_inherited_bia_scope_requires_subcomponent_parent(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "orphan-worker",
                "labels": {
                    "albandrieu.com/operational-state": "active",
                    "albandrieu.com/operational-criticality": "medium",
                    "albandrieu.com/bia-scope": "inherited",
                },
            },
            "spec": {
                "type": "worker",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "component:default/orphan-worker: inherited BIA scope requires "
                "spec.subcomponentOf"
            ],
        )

    def test_active_component_requires_bia_coverage(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "missing-bia",
                "labels": {
                    "albandrieu.com/operational-state": "active",
                    "albandrieu.com/bia-scope": "direct",
                },
            },
            "spec": {
                "type": "service",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "component:default/missing-bia: direct BIA scope requires a "
                "business-criticality label and BIA profile"
            ],
        )

    def test_planned_component_does_not_require_bia_yet(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "planned-service",
                "labels": {
                    "albandrieu.com/operational-state": "planned",
                },
            },
            "spec": {
                "type": "service",
                "lifecycle": "experimental",
                "owner": "group:default/nabla-platform",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [],
        )

    def test_stateful_resource_requires_rpo(self) -> None:
        entity = _entity(
            declared="high",
            mtpd="P1D",
            rto="PT4H",
            rpo="PT1H",
            impact="high",
        )
        entity["kind"] = "Resource"
        entity["metadata"]["name"] = "database"
        entity["metadata"]["labels"][
            "albandrieu.com/operational-state"
        ] = "active"
        del entity["metadata"]["annotations"]["albandrieu.com/bia-rpo"]
        entity["spec"] = {
            "type": "database",
            "owner": "group:default/nabla-platform",
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "resource:default/database: stateful type database requires an "
                "RPO"
            ],
        )

    def test_inherited_bia_scope_allows_dependency_only_criticality(self) -> None:
        entity = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "technical-worker",
                "labels": {
                    "albandrieu.com/operational-state": "active",
                    "albandrieu.com/operational-criticality": "high",
                    "albandrieu.com/bia-scope": "inherited",
                },
            },
            "spec": {
                "type": "worker",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
                "subcomponentOf": "component:default/parent",
            },
        }

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [],
        )

    def test_inherited_bia_scope_rejects_duplicate_own_bia(self) -> None:
        entity = _entity()
        entity["metadata"]["labels"]["albandrieu.com/bia-scope"] = "inherited"
        entity["spec"]["subcomponentOf"] = "component:default/parent"

        self.assertEqual(
            business_continuity_coverage_errors([entity], _policy()),
            [
                "component:default/example: inherited BIA scope must not "
                "duplicate business-criticality or BIA annotations"
            ],
        )

    def test_bia_profile_requires_governance_metadata_and_impact(self) -> None:
        entity = _entity()
        annotations = entity["metadata"]["annotations"]
        del annotations["albandrieu.com/bia-status"]
        del annotations["albandrieu.com/bia-reviewed-at"]
        del annotations["albandrieu.com/bia-mbco"]
        del annotations["albandrieu.com/bia-impact-operational"]

        errors = business_continuity_errors([entity], _policy())

        self.assertEqual(len(errors), 1)
        self.assertIn("MBCO/OMCA", errors[0])
        self.assertIn("assessment status", errors[0])
        self.assertIn("review date", errors[0])

    def test_bia_profile_requires_at_least_one_impact_dimension(self) -> None:
        entity = _entity()
        del entity["metadata"]["annotations"][
            "albandrieu.com/bia-impact-operational"
        ]

        self.assertEqual(
            business_continuity_errors([entity], _policy()),
            [
                "component:default/example: BIA profile requires at least one "
                "impact dimension"
            ],
        )

    def test_dependency_criticality_is_derived_without_mutating_own_bia(self) -> None:
        application = _entity(
            declared="critical",
            mtpd="PT4H",
            rto="PT1H",
            rpo="PT15M",
            impact="critical",
        )
        application["metadata"]["name"] = "application"
        application["spec"]["dependsOn"] = ["resource:default/database"]

        database = _entity(
            declared="low",
            mtpd="P7D",
            rto="P3D",
            rpo="P7D",
            impact="low",
        )
        database["kind"] = "Resource"
        database["metadata"]["name"] = "database"
        database["spec"] = {
            "type": "database",
            "owner": "group:default/nabla-platform",
        }

        rows = effective_dependency_criticality_inventory(
            [application, database],
            _policy(),
        )
        by_ref = {row["entityRef"]: row for row in rows}

        self.assertEqual(
            by_ref["resource:default/database"]["ownBusinessCriticality"],
            "low",
        )
        self.assertEqual(
            by_ref["resource:default/database"][
                "effectiveDependencyCriticality"
            ],
            "critical",
        )
        self.assertTrue(
            by_ref["resource:default/database"]["elevatedByDependencies"]
        )
        self.assertEqual(
            by_ref["resource:default/database"]["inheritedFrom"],
            ["component:default/application"],
        )
        self.assertEqual(
            by_ref["component:default/application"]["ownBusinessCriticality"],
            "critical",
        )
        self.assertFalse(
            by_ref["component:default/application"]["elevatedByDependencies"]
        )

    def test_parent_business_criticality_propagates_to_subcomponent(self) -> None:
        parent = _entity(
            declared="high",
            mtpd="P1D",
            rto="PT4H",
            rpo="PT1H",
            impact="high",
        )
        parent["metadata"]["name"] = "parent"

        child = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "child",
                "labels": {
                    "albandrieu.com/operational-state": "active",
                    "albandrieu.com/operational-criticality": "high",
                    "albandrieu.com/bia-scope": "inherited",
                },
            },
            "spec": {
                "type": "worker",
                "lifecycle": "production",
                "owner": "group:default/nabla-platform",
                "subcomponentOf": "component:default/parent",
            },
        }

        rows = effective_dependency_criticality_inventory(
            [parent, child],
            _policy(),
        )
        by_ref = {row["entityRef"]: row for row in rows}

        self.assertEqual(
            by_ref["component:default/child"]["ownBusinessCriticality"],
            None,
        )
        self.assertEqual(
            by_ref["component:default/child"][
                "effectiveDependencyCriticality"
            ],
            "high",
        )
        self.assertEqual(
            by_ref["component:default/child"]["inheritedFrom"],
            ["component:default/parent"],
        )

    def test_dependency_criticality_propagates_transitively(self) -> None:
        application = _entity(
            declared="critical",
            mtpd="PT4H",
            rto="PT1H",
            rpo="PT15M",
            impact="critical",
        )
        application["metadata"]["name"] = "application"
        application["spec"]["dependsOn"] = ["component:default/middleware"]

        middleware = _entity(
            declared="medium",
            mtpd="P3D",
            rto="P1D",
            rpo="P1D",
            impact="medium",
        )
        middleware["metadata"]["name"] = "middleware"
        middleware["spec"]["dependsOn"] = ["resource:default/database"]

        database = _entity(
            declared="low",
            mtpd="P7D",
            rto="P3D",
            rpo="P7D",
            impact="low",
        )
        database["kind"] = "Resource"
        database["metadata"]["name"] = "database"
        database["spec"] = {
            "type": "database",
            "owner": "group:default/nabla-platform",
        }

        rows = effective_dependency_criticality_inventory(
            [application, middleware, database],
            _policy(),
        )
        by_ref = {row["entityRef"]: row for row in rows}

        self.assertEqual(
            by_ref["component:default/middleware"][
                "effectiveDependencyCriticality"
            ],
            "critical",
        )
        self.assertEqual(
            by_ref["resource:default/database"][
                "effectiveDependencyCriticality"
            ],
            "critical",
        )
        self.assertEqual(
            by_ref["resource:default/database"]["inheritedFrom"],
            ["component:default/application"],
        )

    def test_repository_bia_profiles_are_consistent(self) -> None:
        entities = _repository_entities()
        policy = _policy()
        self.assertEqual(business_continuity_errors(entities, policy), [])
        self.assertEqual(
            business_continuity_coverage_errors(entities, policy),
            [],
        )

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
