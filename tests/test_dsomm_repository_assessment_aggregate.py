from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dsomm" / "aggregate-repository-assessments.py"
SPEC = importlib.util.spec_from_file_location("dsomm_repository_aggregate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
aggregate_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate_module)


ACTIVITY_UUID = "f6f7737f-25a9-4317-8de2-09bf59f29b5b"
MODEL_COMMIT = "a2c1b7e6c7cc22de0d478027d76fd8d02c41fd7a"
MODEL_INDEX = ROOT / "apps" / "dsomm" / "config" / "model-activity-index.json"
ASSESSMENT_SCHEMA = (
    ROOT / "apps" / "dsomm" / "config" / "repository-assessment.schema.json"
)
MODEL_ACTIVITIES = {
    ACTIVITY_UUID: ("Defined build process", "Build and Deployment", 1),
}


def assessment(
    repository: str,
    *,
    score: float | None = 1.0,
    applicability: str = "applicable",
    include_claim: bool = True,
) -> dict:
    progress_by_score = {
        0.0: "not-implemented",
        0.2: "started",
        0.5: "partly-implemented",
        1.0: "fully-implemented",
    }
    claims = []
    if include_claim:
        claims.append(
            {
                "activityUuid": ACTIVITY_UUID,
                "activityName": "Defined build process",
                "dimension": "Build and Deployment",
                "level": 1,
                "applicability": applicability,
                "progress": (
                    None
                    if applicability == "not-applicable"
                    else progress_by_score[score]
                ),
                "score": None if applicability == "not-applicable" else score,
                "scope": "development-process",
                "confidence": "high",
                "rationale": "Synthetic repository evidence for contract tests.",
                "evidenceRefs": ["build"],
            }
        )
    return {
        "$schema": "./nabla-dsomm-assessment.schema.json",
        "schemaVersion": 1,
        "contract": "nabla.dsomm.repository-assessment/v1",
        "subject": {
            "kind": "repository",
            "repository": repository,
            "defaultBranch": "master",
            "url": f"https://github.com/{repository}",
        },
        "assessment": {
            "id": "synthetic-test",
            "assessedAt": "2026-10-05",
            "basisRevision": "1" * 40,
            "method": "evidence-based-self-assessment",
            "reviewStatus": "self-assessed",
            "scope": "repository contract test",
        },
        "model": {
            "project": "OWASP DevSecOps Maturity Model (DSOMM)",
            "version": "5.0.2",
            "sourceCommit": MODEL_COMMIT,
            "activityIdentity": "uuid",
        },
        "progressDefinition": {
            "not-implemented": 0.0,
            "started": 0.2,
            "partly-implemented": 0.5,
            "fully-implemented": 1.0,
        },
        "aggregation": {
            "identity": "activityUuid",
            "excludeApplicability": ["not-applicable"],
            "missingClaim": "not-assessed",
            "modelCompatibility": "exact-source-commit",
            "recommendedPortfolioStrategy": (
                "mean-of-applicable-repository-scores"
            ),
            "notes": "Synthetic aggregation contract.",
        },
        "evidence": [
            {
                "id": "build",
                "type": "test",
                "visibility": "public",
                "title": "Build evidence",
                "description": "Synthetic test evidence.",
                "path": ".github/workflows/ci.yml",
            }
        ],
        "claims": claims,
    }


class DsommRepositoryAssessmentAggregateTests(unittest.TestCase):
    def test_vendored_model_index_is_complete_and_pinned(self) -> None:
        payload = json.loads(MODEL_INDEX.read_text(encoding="utf-8"))

        self.assertEqual(1, payload["schemaVersion"])
        self.assertEqual("5.0.2", payload["model"]["version"])
        self.assertEqual(MODEL_COMMIT, payload["model"]["sourceCommit"])
        self.assertEqual(249, len(payload["activities"]))
        self.assertEqual(
            {
                "name": "Defined build process",
                "dimension": "Build and Deployment",
                "group": "Build",
                "level": 1,
            },
            payload["activities"][ACTIVITY_UUID],
        )
        self.assertEqual(
            "Agentic AI",
            payload["activities"][
                "dc62d384-0b9c-47d9-b7a5-9d82e53642ba"
            ]["dimension"],
        )

    def test_vendored_schema_matches_importer_contract_constants(self) -> None:
        schema = json.loads(ASSESSMENT_SCHEMA.read_text(encoding="utf-8"))
        properties = schema["properties"]

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            aggregate_module.ASSESSMENT_CONTRACT,
            properties["contract"]["const"],
        )
        self.assertEqual(
            aggregate_module.SCHEMA_REF,
            properties["$schema"]["const"],
        )
        self.assertEqual(
            aggregate_module.MODEL_PROJECT,
            properties["model"]["properties"]["project"]["const"],
        )
        self.assertEqual(
            aggregate_module.REVIEW_STATUSES,
            set(
                properties["assessment"]["properties"]["reviewStatus"]["enum"]
            ),
        )
        self.assertEqual(
            aggregate_module.CLAIM_SCOPES,
            set(properties["claims"]["items"]["properties"]["scope"]["enum"]),
        )
        self.assertEqual(
            aggregate_module.EVIDENCE_TYPES,
            set(properties["evidence"]["items"]["properties"]["type"]["enum"]),
        )
        self.assertEqual(
            aggregate_module.EVIDENCE_VISIBILITIES,
            set(
                properties["evidence"]["items"]["properties"]["visibility"][
                    "enum"
                ]
            ),
        )

    def test_missing_repository_claim_is_not_converted_to_zero(self) -> None:
        contexts = {
            "AlbanAndrieu/nabla-site-alban": "Nabla Applications",
            "AlbanAndrieu/fastapi-sample": "Nabla Applications",
        }
        site = assessment("AlbanAndrieu/nabla-site-alban", score=1.0)
        aggregate_module.validate_assessment(
            site,
            expected_repository="AlbanAndrieu/nabla-site-alban",
            model_version="5.0.2",
            model_source_commit=MODEL_COMMIT,
            model_activities=MODEL_ACTIVITIES,
        )

        portfolio = aggregate_module.aggregate(
            contexts=contexts,
            assessments={"AlbanAndrieu/nabla-site-alban": site},
            model_version="5.0.2",
            model_source_commit=MODEL_COMMIT,
        )
        activity = portfolio["contexts"]["Nabla Applications"]["activities"][0]

        self.assertEqual(1.0, activity["averageProgress"])
        self.assertFalse(activity["assessmentCoverage"]["complete"])
        self.assertEqual(
            ["AlbanAndrieu/fastapi-sample"],
            activity["assessmentCoverage"]["missingRepositories"],
        )
        self.assertIsNone(activity["recommendedDsommState"])

    def test_complete_context_excludes_not_applicable_from_average(self) -> None:
        contexts = {
            "AlbanAndrieu/nabla-site-alban": "Nabla Applications",
            "AlbanAndrieu/fastapi-sample": "Nabla Applications",
            "AlbanAndrieu/nabla-site-bababou": "Nabla Applications",
        }
        assessments = {
            "AlbanAndrieu/nabla-site-alban": assessment(
                "AlbanAndrieu/nabla-site-alban",
                score=1.0,
            ),
            "AlbanAndrieu/fastapi-sample": assessment(
                "AlbanAndrieu/fastapi-sample",
                score=0.5,
            ),
            "AlbanAndrieu/nabla-site-bababou": assessment(
                "AlbanAndrieu/nabla-site-bababou",
                score=None,
                applicability="not-applicable",
            ),
        }

        portfolio = aggregate_module.aggregate(
            contexts=contexts,
            assessments=assessments,
            model_version="5.0.2",
            model_source_commit=MODEL_COMMIT,
        )
        activity = portfolio["contexts"]["Nabla Applications"]["activities"][0]

        self.assertTrue(activity["assessmentCoverage"]["complete"])
        self.assertEqual(0.75, activity["averageProgress"])
        self.assertEqual("Partly implemented", activity["recommendedDsommState"])
        self.assertEqual(
            ["AlbanAndrieu/nabla-site-bababou"],
            activity["notApplicableRepositories"],
        )
        self.assertEqual(2, activity["applicableRepositories"])

    def test_import_fails_closed_on_model_commit_mismatch(self) -> None:
        site = assessment("AlbanAndrieu/nabla-site-alban")
        site["model"]["sourceCommit"] = "b" * 40

        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "sourceCommit",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository="AlbanAndrieu/nabla-site-alban",
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

    def test_source_loader_rejects_downgrade_redirect(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "http://producer.invalid/assessment.json"
        response.read.return_value = b"{}"

        with patch.object(aggregate_module, "urlopen", return_value=response):
            with self.assertRaisesRegex(
                aggregate_module.AssessmentError,
                "redirect target must remain HTTPS",
            ):
                aggregate_module.load_json_source(
                    "https://producer.invalid/assessment.json"
                )

    def test_source_loader_rejects_oversized_remote_and_local_input(self) -> None:
        oversized = b"x" * (aggregate_module.MAX_SOURCE_BYTES + 1)
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "https://producer.invalid/assessment.json"
        response.read.return_value = oversized

        with patch.object(aggregate_module, "urlopen", return_value=response):
            with self.assertRaisesRegex(
                aggregate_module.AssessmentError,
                "assessment source exceeds",
            ):
                aggregate_module.load_json_source(
                    "https://producer.invalid/assessment.json"
                )

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "assessment.json"
            source.write_bytes(oversized)
            with self.assertRaisesRegex(
                aggregate_module.AssessmentError,
                "assessment source exceeds",
            ):
                aggregate_module.load_json_source(str(source))

    def test_source_loader_reports_invalid_utf8_json_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "assessment.json"
            source.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(
                aggregate_module.AssessmentError,
                "invalid UTF-8 JSON assessment",
            ):
                aggregate_module.load_json_source(str(source))

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "assessment.json"
            source.write_text(json.dumps({"valid": True}), encoding="utf-8")
            self.assertEqual(
                {"valid": True},
                aggregate_module.load_json_source(str(source)),
            )

    def test_import_rejects_schema_metadata_drift(self) -> None:
        repository = "AlbanAndrieu/nabla-site-alban"
        mutations = (
            ("reviewStatus", "unreviewed", "reviewStatus"),
            ("method", "manual", "assessment method"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                site = assessment(repository)
                site["assessment"][field] = value
                with self.assertRaisesRegex(
                    aggregate_module.AssessmentError,
                    expected,
                ):
                    aggregate_module.validate_assessment(
                        site,
                        expected_repository=repository,
                        model_version="5.0.2",
                        model_source_commit=MODEL_COMMIT,
                        model_activities=MODEL_ACTIVITIES,
                    )

        site = assessment(repository)
        site["unexpected"] = True
        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "unsupported fields",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository=repository,
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

    def test_import_rejects_invalid_evidence_and_claim_scope(self) -> None:
        repository = "AlbanAndrieu/nabla-site-alban"

        site = assessment(repository)
        site["evidence"][0]["visibility"] = "private"
        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "evidence visibility",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository=repository,
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

        site = assessment(repository)
        site["evidence"][0]["url"] = "https://example.invalid/evidence"
        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "exactly one of path or url",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository=repository,
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

        site = assessment(repository)
        site["claims"][0]["scope"] = "unknown"
        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "invalid scope",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository=repository,
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

    def test_import_rejects_activity_outside_reviewed_seed(self) -> None:
        site = assessment("AlbanAndrieu/nabla-site-alban")
        site["claims"][0]["activityUuid"] = "11111111-1111-4111-8111-111111111111"

        with self.assertRaisesRegex(
            aggregate_module.AssessmentError,
            "not in the reviewed DSOMM model index",
        ):
            aggregate_module.validate_assessment(
                site,
                expected_repository="AlbanAndrieu/nabla-site-alban",
                model_version="5.0.2",
                model_source_commit=MODEL_COMMIT,
                model_activities=MODEL_ACTIVITIES,
            )

    def test_import_rejects_canonical_name_or_level_drift(self) -> None:
        repository = "AlbanAndrieu/nabla-site-alban"
        for field, value, expected in (
            ("activityName", "Invented build process", "activityName"),
            ("dimension", "Invented dimension", "dimension"),
            ("level", 5, "level"),
        ):
            with self.subTest(field=field):
                site = assessment(repository)
                site["claims"][0][field] = value
                with self.assertRaisesRegex(
                    aggregate_module.AssessmentError,
                    expected,
                ):
                    aggregate_module.validate_assessment(
                        site,
                        expected_repository=repository,
                        model_version="5.0.2",
                        model_source_commit=MODEL_COMMIT,
                        model_activities=MODEL_ACTIVITIES,
                    )

    def test_repository_evidence_is_preserved_with_producer_reference(self) -> None:
        repository = "AlbanAndrieu/nabla-site-alban"
        portfolio = aggregate_module.aggregate(
            contexts={repository: "Nabla Applications"},
            assessments={repository: assessment(repository)},
            model_version="5.0.2",
            model_source_commit=MODEL_COMMIT,
        )
        evidence = portfolio["contexts"]["Nabla Applications"]["activities"][0][
            "repositories"
        ][0]["evidence"][0]

        self.assertEqual(f"{repository}#build", evidence["producerRef"])
        self.assertEqual("Build evidence", evidence["title"])


if __name__ == "__main__":
    unittest.main()
