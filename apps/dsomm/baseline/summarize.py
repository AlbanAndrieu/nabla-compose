"""Summarize Tweag dsomm-baseline CSV output for human DSOMM review."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

NEGATIVE = {
    "not detected",
    "no",
    "not available",
    "not enabled",
    "unable to check",
    "error parsing data",
    "error exception",
    "error",
}
MANUAL = "not supported - manual process"


def classify(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == MANUAL:
        return "manual"
    if normalized in NEGATIVE or normalized.startswith("error"):
        return "gap"
    if not normalized:
        return "unknown"
    return "detected"


def load_context_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repositories = payload.get("repositories", {})
    if not isinstance(repositories, dict):
        raise ValueError("repository context map must contain a repositories mapping")
    return {
        str(repo): str(context)
        for repo, context in repositories.items()
        if str(repo).strip() and str(context).strip()
    }


def summarize(
    csv_path: Path,
    output_path: Path,
    context_map_path: Path | None = None,
) -> None:
    context_map = load_context_map(context_map_path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or len(rows[0]) < 2 or rows[0][0] != "Security Feature":
        raise ValueError("unexpected dsomm-baseline CSV header")

    repos = rows[0][1:]
    findings: dict[str, dict[str, list[tuple[str, str]]]] = {
        repo: {"detected": [], "gap": [], "manual": [], "unknown": []}
        for repo in repos
    }
    scores: list[list[str]] = []

    for row in rows[1:]:
        if not row:
            continue
        feature = row[0].strip()
        if feature.endswith(" Score"):
            scores.append(row)
            continue
        for index, repo in enumerate(repos, start=1):
            value = row[index].strip() if index < len(row) else ""
            findings[repo][classify(value)].append((feature, value))

    lines = [
        "# DSOMM baseline review",
        "",
        "> Automated GitHub evidence only. This is not an OWASP DSOMM maturity verdict.",
        "> Manual/process/interview activities still require reviewed human evidence.",
        "",
    ]

    if scores:
        lines.extend(["## Upstream automated scores", ""])
        for row in scores:
            rendered = " · ".join(
                f"{repo}: {row[index] if index < len(row) else ''}"
                for index, repo in enumerate(repos, start=1)
            )
            lines.append(f"- **{row[0]}** — {rendered}")
        lines.append("")

    for repo in repos:
        context = context_map.get(repo)
        title = f"## {repo}" if not context else f"## {repo} → {context}"
        lines.extend([title, ""])
        if context:
            lines.extend(
                [
                    f"- **DSOMM context:** `{context}`",
                    (
                        "- **Action:** review detected evidence, then attach it to "
                        "the matching DSOMM activity in the UI."
                    ),
                    "",
                ]
            )
        sections = (
            ("Detected automated evidence", "detected"),
            ("Automated gaps / unavailable evidence", "gap"),
            ("Manual DSOMM evidence required", "manual"),
            ("Unknown / empty result", "unknown"),
        )
        for title, key in sections:
            lines.extend([f"### {title}", ""])
            entries = findings[repo][key]
            if not entries:
                lines.append("- None")
            else:
                for feature, value in entries:
                    rendered = value or "empty result"
                    lines.append(f"- [ ] **{feature}** — {rendered}")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--context-map", type=Path, default=None)
    args = parser.parse_args()
    summarize(args.csv, args.output, args.context_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
