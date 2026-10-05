#!/usr/bin/env python3
"""Aggregate repository-level DSOMM assessments without collapsing provenance."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT_MAP = ROOT / "apps" / "dsomm" / "config" / "repository-contexts.yaml"
DEFAULT_MODEL = ROOT / "apps" / "dsomm" / "config" / "seed-activities.yaml"
ASSESSMENT_CONTRACT = "nabla.dsomm.repository-assessment/v1"
PORTFOLIO_CONTRACT = "nabla.dsomm.portfolio-assessment/v1"
PROGRESS_SCORES = {
    "not-implemented": 0.0,
    "started": 0.2,
    "partly-implemented": 0.5,
    "fully-implemented": 1.0,
}
MAX_SOURCE_BYTES = 1024 * 1024
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}(?:-(?:medium|advanced))?$",
    re.IGNORECASE,
)


class AssessmentError(ValueError):
    """Raised when a producer assessment violates the import contract."""


def fail(message: str) -> None:
    raise AssessmentError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail(f"{path}: expected a YAML mapping")
    return payload


def load_json_source(locator: str, *, timeout_seconds: int = 10) -> dict[str, Any]:
    if locator.startswith("https://"):
        request = Request(
            locator,
            headers={"User-Agent": "nabla-compose-dsomm-aggregator/1"},
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            final_url = response.geturl()
            if urlsplit(final_url).scheme.lower() != "https":
                fail(f"{locator}: redirect target must remain HTTPS")
            raw = response.read(MAX_SOURCE_BYTES + 1)
    elif "://" in locator:
        fail(f"{locator}: only HTTPS URLs or local paths are accepted")
    else:
        path = Path(locator)
        if path.stat().st_size > MAX_SOURCE_BYTES:
            fail(
                f"{locator}: assessment source exceeds "
                f"{MAX_SOURCE_BYTES} bytes"
            )
        raw = path.read_bytes()

    if len(raw) > MAX_SOURCE_BYTES:
        fail(f"{locator}: assessment source exceeds {MAX_SOURCE_BYTES} bytes")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssessmentError(f"{locator}: invalid UTF-8 JSON assessment") from exc
    if not isinstance(payload, dict):
        fail(f"{locator}: expected a JSON object")
    return payload


def parse_source_arg(value: str) -> tuple[str, str]:
    repository, separator, locator = value.partition("=")
    if not separator or "/" not in repository or not locator:
        raise argparse.ArgumentTypeError(
            "--source must use owner/repository=/path/or/https-url"
        )
    return repository, locator


def load_model_contract(
    path: Path,
) -> tuple[str, str, dict[str, tuple[str, int]]]:
    payload = load_yaml(path)
    model = payload.get("model")
    if not isinstance(model, dict):
        fail(f"{path}: model mapping is required")
    version = str(model.get("version", "")).strip()
    source_commit = str(model.get("sourceCommit", "")).strip()
    if not version:
        fail(f"{path}: model.version is required")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        fail(f"{path}: model.sourceCommit must be a full Git SHA")

    activities = payload.get("activities")
    if not isinstance(activities, dict) or not activities:
        fail(f"{path}: activities mapping is required")

    activity_contract: dict[str, tuple[str, int]] = {}
    for activity_uuid, activity in activities.items():
        if not isinstance(activity_uuid, str) or not UUID_RE.fullmatch(activity_uuid):
            fail(f"{path}: invalid canonical activity UUID {activity_uuid!r}")
        if not isinstance(activity, dict):
            fail(f"{path}: activity {activity_uuid} must be a mapping")
        name = activity.get("name")
        level = activity.get("level")
        if not isinstance(name, str) or not name.strip():
            fail(f"{path}: activity {activity_uuid} name is required")
        if not isinstance(level, int) or not 1 <= level <= 5:
            fail(f"{path}: activity {activity_uuid} level must be 1..5")
        activity_contract[activity_uuid] = (name.strip(), level)

    return version, source_commit, activity_contract


def load_contexts(path: Path) -> dict[str, str]:
    payload = load_yaml(path)
    repositories = payload.get("repositories")
    if not isinstance(repositories, dict) or not repositories:
        fail(f"{path}: repositories mapping is required")
    result: dict[str, str] = {}
    for repository, context in repositories.items():
        if not isinstance(repository, str) or "/" not in repository:
            fail(f"{path}: invalid repository key {repository!r}")
        if not isinstance(context, str) or not context.strip():
            fail(f"{path}: invalid context for {repository}")
        result[repository] = context.strip()
    return result


def validate_assessment(
    payload: dict[str, Any],
    *,
    expected_repository: str,
    model_version: str,
    model_source_commit: str,
    model_activities: dict[str, tuple[str, int]],
) -> dict[str, Any]:
    if payload.get("schemaVersion") != 1:
        fail(f"{expected_repository}: schemaVersion must be 1")
    if payload.get("contract") != ASSESSMENT_CONTRACT:
        fail(f"{expected_repository}: unsupported contract")

    subject = payload.get("subject")
    if not isinstance(subject, dict) or subject.get("kind") != "repository":
        fail(f"{expected_repository}: subject.kind must be repository")
    if subject.get("repository") != expected_repository:
        fail(
            f"{expected_repository}: producer subject is "
            f"{subject.get('repository')!r}"
        )

    assessment_info = payload.get("assessment")
    if not isinstance(assessment_info, dict):
        fail(f"{expected_repository}: assessment mapping is required")
    assessed_at = assessment_info.get("assessedAt")
    if not isinstance(assessed_at, str):
        fail(f"{expected_repository}: assessment.assessedAt is required")
    try:
        date.fromisoformat(assessed_at)
    except ValueError as exc:
        raise AssessmentError(
            f"{expected_repository}: assessment.assessedAt must be an ISO date"
        ) from exc
    basis_revision = assessment_info.get("basisRevision")
    if not isinstance(basis_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}",
        basis_revision,
    ):
        fail(
            f"{expected_repository}: assessment.basisRevision must be a full Git SHA"
        )

    model = payload.get("model")
    if not isinstance(model, dict):
        fail(f"{expected_repository}: model mapping is required")
    if str(model.get("version")) != model_version:
        fail(
            f"{expected_repository}: model version {model.get('version')!r} "
            f"does not match portfolio {model_version}"
        )
    if model.get("sourceCommit") != model_source_commit:
        fail(
            f"{expected_repository}: model sourceCommit does not match "
            "the portfolio target"
        )
    if model.get("activityIdentity") != "uuid":
        fail(f"{expected_repository}: activityIdentity must be uuid")

    progress_definition = payload.get("progressDefinition")
    if progress_definition != PROGRESS_SCORES:
        fail(
            f"{expected_repository}: progressDefinition must match the "
            "DSOMM 0/20/50/100 scale"
        )

    aggregation = payload.get("aggregation")
    if not isinstance(aggregation, dict):
        fail(f"{expected_repository}: aggregation mapping is required")
    if aggregation.get("identity") != "activityUuid":
        fail(f"{expected_repository}: aggregation identity must be activityUuid")
    if aggregation.get("missingClaim") != "not-assessed":
        fail(f"{expected_repository}: missing claims must remain not-assessed")
    if aggregation.get("modelCompatibility") != "exact-source-commit":
        fail(
            f"{expected_repository}: producer must require exact-source-commit "
            "compatibility"
        )

    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        fail(f"{expected_repository}: evidence must be a list")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for entry in evidence:
        if not isinstance(entry, dict):
            fail(f"{expected_repository}: evidence entries must be objects")
        evidence_id = entry.get("id")
        if not isinstance(evidence_id, str) or not evidence_id:
            fail(f"{expected_repository}: evidence id is required")
        if evidence_id in evidence_by_id:
            fail(f"{expected_repository}: duplicate evidence id {evidence_id}")
        evidence_by_id[evidence_id] = entry

    claims = payload.get("claims")
    if not isinstance(claims, list):
        fail(f"{expected_repository}: claims must be a list")
    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            fail(f"{expected_repository}: claim entries must be objects")
        activity_uuid = claim.get("activityUuid")
        if not isinstance(activity_uuid, str) or not UUID_RE.fullmatch(activity_uuid):
            fail(f"{expected_repository}: invalid activity UUID {activity_uuid!r}")
        if activity_uuid in claim_ids:
            fail(f"{expected_repository}: duplicate claim {activity_uuid}")
        claim_ids.add(activity_uuid)

        canonical_activity = model_activities.get(activity_uuid)
        if canonical_activity is None:
            fail(
                f"{expected_repository}: activity UUID {activity_uuid} is not "
                "in the reviewed portfolio seed"
            )
        canonical_name, canonical_level = canonical_activity
        if claim.get("activityName") != canonical_name:
            fail(
                f"{expected_repository}/{activity_uuid}: activityName must be "
                f"{canonical_name!r}"
            )
        if claim.get("level") != canonical_level:
            fail(
                f"{expected_repository}/{activity_uuid}: level must be "
                f"{canonical_level}"
            )

        applicability = claim.get("applicability")
        if applicability not in {"applicable", "not-applicable"}:
            fail(
                f"{expected_repository}/{activity_uuid}: invalid applicability"
            )
        progress = claim.get("progress")
        score = claim.get("score")
        if applicability == "not-applicable":
            if progress is not None or score is not None:
                fail(
                    f"{expected_repository}/{activity_uuid}: N/A claim must "
                    "have null progress and score"
                )
        else:
            if progress not in PROGRESS_SCORES:
                fail(
                    f"{expected_repository}/{activity_uuid}: invalid progress "
                    f"{progress!r}"
                )
            if score != PROGRESS_SCORES[progress]:
                fail(
                    f"{expected_repository}/{activity_uuid}: score does not "
                    "match progress"
                )

        confidence = claim.get("confidence")
        if confidence not in {"low", "medium", "high"}:
            fail(
                f"{expected_repository}/{activity_uuid}: invalid confidence"
            )
        if not isinstance(claim.get("dimension"), str):
            fail(f"{expected_repository}/{activity_uuid}: dimension is required")
        if not isinstance(claim.get("level"), int):
            fail(f"{expected_repository}/{activity_uuid}: level is required")
        if not isinstance(claim.get("rationale"), str):
            fail(f"{expected_repository}/{activity_uuid}: rationale is required")

        refs = claim.get("evidenceRefs")
        if not isinstance(refs, list) or not refs:
            fail(
                f"{expected_repository}/{activity_uuid}: evidenceRefs must "
                "be non-empty"
            )
        unknown = [ref for ref in refs if ref not in evidence_by_id]
        if unknown:
            fail(
                f"{expected_repository}/{activity_uuid}: unknown evidence "
                f"{unknown}"
            )
    return payload


def conservative_state(score: float) -> str:
    if score >= 1:
        return "Fully implemented"
    if score >= 0.5:
        return "Partly implemented"
    if score > 0:
        return "Started"
    return "Not implemented"


def aggregate(
    *,
    contexts: dict[str, str],
    assessments: dict[str, dict[str, Any]],
    model_version: str,
    model_source_commit: str,
) -> dict[str, Any]:
    unknown_sources = set(assessments) - set(contexts)
    if unknown_sources:
        fail(
            "assessments provided for repositories absent from context map: "
            + ", ".join(sorted(unknown_sources))
        )

    configured_by_context: dict[str, list[str]] = defaultdict(list)
    for repository, context in contexts.items():
        configured_by_context[context].append(repository)
    for repositories in configured_by_context.values():
        repositories.sort()

    activity_metadata: dict[str, tuple[str, str, int]] = {}
    claims_by_context: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    evidence_by_repository = {
        repository: {
            entry["id"]: entry
            for entry in assessment.get("evidence", [])
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        for repository, assessment in assessments.items()
    }

    for repository, assessment in assessments.items():
        context = contexts[repository]
        for claim in assessment["claims"]:
            activity_uuid = claim["activityUuid"]
            metadata = (
                claim["activityName"],
                claim["dimension"],
                claim["level"],
            )
            previous = activity_metadata.setdefault(activity_uuid, metadata)
            if previous != metadata:
                fail(
                    f"{activity_uuid}: producer metadata mismatch "
                    f"{previous!r} != {metadata!r}"
                )
            claims_by_context[context][activity_uuid][repository] = claim

    context_output: dict[str, Any] = {}
    for context in sorted(configured_by_context):
        configured = configured_by_context[context]
        imported = sorted(repo for repo in configured if repo in assessments)
        activities: list[dict[str, Any]] = []
        for activity_uuid in sorted(claims_by_context.get(context, {})):
            repo_claims = claims_by_context[context][activity_uuid]
            assessed_repositories = sorted(repo_claims)
            missing_repositories = sorted(set(configured) - set(repo_claims))
            applicable = [
                (repository, claim)
                for repository, claim in repo_claims.items()
                if claim["applicability"] == "applicable"
            ]
            not_applicable = sorted(
                repository
                for repository, claim in repo_claims.items()
                if claim["applicability"] == "not-applicable"
            )
            scores = [float(claim["score"]) for _, claim in applicable]
            average = sum(scores) / len(scores) if scores else None
            complete = not missing_repositories
            state = (
                conservative_state(average)
                if complete and average is not None
                else None
            )
            name, dimension, level = activity_metadata[activity_uuid]
            repositories: list[dict[str, Any]] = []
            for repository in assessed_repositories:
                claim = repo_claims[repository]
                repository_evidence = evidence_by_repository[repository]
                repositories.append(
                    {
                        "repository": repository,
                        "applicability": claim["applicability"],
                        "progress": claim["progress"],
                        "score": claim["score"],
                        "confidence": claim["confidence"],
                        "rationale": claim["rationale"],
                        "evidence": [
                            {
                                **repository_evidence[ref],
                                "producerRef": f"{repository}#{ref}",
                            }
                            for ref in claim["evidenceRefs"]
                        ],
                    }
                )
            activities.append(
                {
                    "activityUuid": activity_uuid,
                    "activityName": name,
                    "dimension": dimension,
                    "level": level,
                    "assessmentCoverage": {
                        "configuredRepositories": len(configured),
                        "assessedRepositories": len(assessed_repositories),
                        "complete": complete,
                        "missingRepositories": missing_repositories,
                    },
                    "applicableRepositories": len(applicable),
                    "notApplicableRepositories": not_applicable,
                    "averageProgress": average,
                    "recommendedDsommState": state,
                    "repositories": repositories,
                }
            )
        context_output[context] = {
            "configuredRepositories": configured,
            "importedRepositories": imported,
            "sourceCoverage": {
                "configured": len(configured),
                "imported": len(imported),
                "complete": len(imported) == len(configured),
                "missingRepositories": sorted(set(configured) - set(imported)),
            },
            "activities": activities,
        }

    producer_assessments = {
        repository: {
            "context": contexts[repository],
            "assessedAt": assessment["assessment"]["assessedAt"],
            "basisRevision": assessment["assessment"]["basisRevision"],
            "reviewStatus": assessment["assessment"].get("reviewStatus"),
        }
        for repository, assessment in sorted(assessments.items())
    }

    return {
        "schemaVersion": 1,
        "contract": PORTFOLIO_CONTRACT,
        "model": {
            "project": "OWASP DevSecOps Maturity Model (DSOMM)",
            "version": model_version,
            "sourceCommit": model_source_commit,
            "activityIdentity": "uuid",
        },
        "aggregation": {
            "strategy": "mean-of-applicable-repository-scores",
            "missingClaim": "not-assessed",
            "notApplicable": "excluded",
            "recommendedStateRequiresCompleteActivityCoverage": True,
        },
        "repositories": {
            "configured": sorted(contexts),
            "imported": sorted(assessments),
            "missing": sorted(set(contexts) - set(assessments)),
        },
        "producerAssessments": producer_assessments,
        "contexts": context_output,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate evidence-based repository DSOMM assessments"
    )
    parser.add_argument(
        "--context-map",
        type=Path,
        default=DEFAULT_CONTEXT_MAP,
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        type=parse_source_arg,
        metavar="OWNER/REPO=PATH_OR_URL",
        help="Repository assessment source; repeat for each producer",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.source:
        parser.error("at least one --source is required")

    try:
        contexts = load_contexts(args.context_map)
        (
            model_version,
            model_source_commit,
            model_activities,
        ) = load_model_contract(args.model)
        assessments: dict[str, dict[str, Any]] = {}
        for repository, locator in args.source:
            if repository in assessments:
                fail(f"duplicate --source for {repository}")
            payload = load_json_source(locator)
            assessments[repository] = validate_assessment(
                payload,
                expected_repository=repository,
                model_version=model_version,
                model_source_commit=model_source_commit,
                model_activities=model_activities,
            )
        portfolio = aggregate(
            contexts=contexts,
            assessments=assessments,
            model_version=model_version,
            model_source_commit=model_source_commit,
        )
        write_json(args.output, portfolio)
    except (OSError, json.JSONDecodeError, yaml.YAMLError, AssessmentError) as exc:
        print(f"DSOMM_REPOSITORY_AGGREGATE_INVALID: {exc}", file=sys.stderr)
        return 1

    print(
        "OK: aggregated "
        f"{len(portfolio['repositories']['imported'])}/"
        f"{len(portfolio['repositories']['configured'])} repository "
        f"assessment source(s) into {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
