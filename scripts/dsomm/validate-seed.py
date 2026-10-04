"""Validate the repository-owned DSOMM assessment seed without network access."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import re
import sys
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_META = ROOT / "apps" / "dsomm" / "config" / "meta.yaml"
DEFAULT_ACTIVITIES = ROOT / "apps" / "dsomm" / "config" / "seed-activities.yaml"
DEFAULT_PROGRESS = ROOT / "apps" / "dsomm" / "config" / "team-progress.seed.yaml"
DEFAULT_EVIDENCE = ROOT / "apps" / "dsomm" / "config" / "team-evidence.seed.yaml"
EXPECTED_MODEL_VERSION = "5.0.2"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(message: str) -> None:
    raise ValueError(message)


def load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail(f"{path}: expected a YAML mapping")
    return payload


def is_iso_date(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    return isinstance(value, str) and ISO_DATE.fullmatch(value) is not None


def validate(
    meta_path: Path,
    activities_path: Path,
    progress_path: Path,
    evidence_path: Path,
) -> tuple[int, int]:
    meta = load_yaml(meta_path)
    catalog = load_yaml(activities_path)
    progress_doc = load_yaml(progress_path)
    evidence_doc = load_yaml(evidence_path)

    teams = meta.get("teams")
    if not isinstance(teams, list) or not teams or not all(isinstance(x, str) for x in teams):
        fail("meta.yaml: teams must be a non-empty string list")
    known_teams = set(teams)

    progress_definition = meta.get("progressDefinition")
    if not isinstance(progress_definition, dict) or not progress_definition:
        fail("meta.yaml: progressDefinition must be a non-empty mapping")

    states_by_score: list[tuple[float, str]] = []
    for state, definition in progress_definition.items():
        if not isinstance(state, str) or not isinstance(definition, dict):
            fail("meta.yaml: invalid progressDefinition entry")
        score = definition.get("score")
        if isinstance(score, str) and score.endswith("%"):
            numeric = float(score[:-1]) / 100
        elif isinstance(score, (int, float)):
            numeric = float(score)
        else:
            fail(f"meta.yaml: invalid score for progress state {state}")
        states_by_score.append((numeric, state))
    states_by_score.sort()
    if states_by_score[0][0] != 0 or states_by_score[-1][0] != 1:
        fail("meta.yaml: progress scale must contain 0% and 100% states")
    nonzero_states = [state for score, state in states_by_score if score > 0]

    model = catalog.get("model")
    if not isinstance(model, dict) or str(model.get("version")) != EXPECTED_MODEL_VERSION:
        fail(f"seed activity catalog must target DSOMM {EXPECTED_MODEL_VERSION}")

    activities = catalog.get("activities")
    if not isinstance(activities, dict) or not activities:
        fail("seed activity catalog must contain activities")
    for activity_uuid, activity in activities.items():
        try:
            uuid.UUID(str(activity_uuid))
        except ValueError as exc:
            raise ValueError(
                f"invalid DSOMM activity UUID: {activity_uuid}"
            ) from exc
        if not isinstance(activity, dict) or not str(activity.get("name", "")).strip():
            fail(f"{activity_uuid}: activity name is required")
        level = activity.get("level")
        if not isinstance(level, int) or not 1 <= level <= 5:
            fail(f"{activity_uuid}: activity level must be 1..5")

    progress = progress_doc.get("progress")
    if not isinstance(progress, dict) or not progress:
        fail("team-progress.seed.yaml: progress must be non-empty")

    for activity_uuid, team_progress in progress.items():
        if activity_uuid not in activities:
            fail(f"progress references unreviewed activity UUID {activity_uuid}")
        if not isinstance(team_progress, dict) or not team_progress:
            fail(f"{activity_uuid}: progress must contain at least one context")
        for team, states in team_progress.items():
            if team not in known_teams:
                fail(f"{activity_uuid}: unknown DSOMM context {team}")
            if not isinstance(states, dict) or not states:
                fail(f"{activity_uuid}/{team}: progress states must be non-empty")
            unknown_states = set(states) - set(nonzero_states)
            if unknown_states:
                fail(
                    f"{activity_uuid}/{team}: unsupported progress states "
                    f"{sorted(unknown_states)}"
                )
            indexes = sorted(nonzero_states.index(state) for state in states)
            if indexes != list(range(indexes[-1] + 1)):
                fail(
                    f"{activity_uuid}/{team}: progress must contain every preceding "
                    "state up to the selected maturity state"
                )
            for state, recorded in states.items():
                if not is_iso_date(recorded):
                    fail(f"{activity_uuid}/{team}/{state}: expected ISO date")

    evidence = evidence_doc.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        fail("team-evidence.seed.yaml: evidence must be non-empty")

    seen_ids: set[str] = set()
    for activity_uuid, entries in evidence.items():
        if activity_uuid not in activities:
            fail(f"evidence references unreviewed activity UUID {activity_uuid}")
        if activity_uuid not in progress:
            fail(f"{activity_uuid}: evidence exists without seeded progress")
        if not isinstance(entries, list) or not entries:
            fail(f"{activity_uuid}: evidence must be a non-empty list")

        progressed_teams = set(progress[activity_uuid])
        for entry in entries:
            if not isinstance(entry, dict):
                fail(f"{activity_uuid}: evidence entry must be a mapping")
            evidence_id = str(entry.get("id", ""))
            try:
                uuid.UUID(evidence_id)
            except ValueError as exc:
                fail(f"{activity_uuid}: invalid evidence UUID {evidence_id}") from exc
            if evidence_id in seen_ids:
                fail(f"duplicate evidence UUID {evidence_id}")
            seen_ids.add(evidence_id)

            entry_teams = entry.get("teams")
            if (
                not isinstance(entry_teams, list)
                or not entry_teams
                or not all(isinstance(team, str) for team in entry_teams)
            ):
                fail(f"{activity_uuid}/{evidence_id}: teams must be a non-empty list")
            unknown_teams = set(entry_teams) - known_teams
            if unknown_teams:
                fail(
                    f"{activity_uuid}/{evidence_id}: unknown contexts "
                    f"{sorted(unknown_teams)}"
                )
            if not set(entry_teams) <= progressed_teams:
                fail(
                    f"{activity_uuid}/{evidence_id}: evidence context lacks seeded progress"
                )

            for field in ("title", "description"):
                if not str(entry.get(field, "")).strip():
                    fail(f"{activity_uuid}/{evidence_id}: {field} is required")
            if not is_iso_date(entry.get("evidenceRecorded")):
                fail(f"{activity_uuid}/{evidence_id}: evidenceRecorded must be ISO date")

            attachments = entry.get("attachment", [])
            if not isinstance(attachments, list):
                fail(f"{activity_uuid}/{evidence_id}: attachment must be a list")
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    fail(f"{activity_uuid}/{evidence_id}: invalid attachment")
                link = attachment.get("externalLink")
                if attachment.get("type") != "link" or not isinstance(link, str):
                    fail(f"{activity_uuid}/{evidence_id}: only link attachments are seeded")
                if not link.startswith("https://"):
                    fail(f"{activity_uuid}/{evidence_id}: attachment must use HTTPS")

    missing_evidence = set(progress) - set(evidence)
    if missing_evidence:
        fail(
            "seeded progress without evidence for UUIDs: "
            + ", ".join(sorted(missing_evidence))
        )

    return len(progress), len(seen_ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--activities", type=Path, default=DEFAULT_ACTIVITIES)
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()

    try:
        activity_count, evidence_count = validate(
            args.meta,
            args.activities,
            args.progress,
            args.evidence,
        )
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"DSOMM_SEED_INVALID: {exc}", file=sys.stderr)
        return 1

    print(
        "OK: DSOMM 5.0.2 seed is internally consistent "
        f"({activity_count} activities, {evidence_count} evidence records)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
