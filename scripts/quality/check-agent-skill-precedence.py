#!/usr/bin/env python3
"""Fail-closed, read-only check of Nabla agent skill and architecture policy.

Read a small fixed set of tracked Markdown/Just files. Do not load secrets,
run shell commands, install skills or contact services.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

# Path -> (exact policy heading or None, markers that must remain together).
# Check only the relevant section; a keyword elsewhere must not mask drift.
REQUIRED: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "AGENTS.md": (
        "## Required skill precedence for the Nabla homelab",
        (
            "docs/agent-skills-architecture.md",
            "Nabla project skills",
            "externally installed skills",
            "docker-compose-patterns",
            "kubernetes-specialist",
            "/mnt/cpool/<service>",
            "/mnt/cpool/secrets/runtime/<service>/",
            "Vaultwarden",
            "democratic-csi",
            "Do not run",
            "Ask the user before installing",
        ),
    ),
    "docs/agent-skills-architecture.md": (
        None,
        (
            "## Instruction precedence inside this repository",
            "## Decisions: TrueNAS and Docker Compose",
            "## Decisions: Talos/Kubernetes target",
            "## Catalog ownership and site/API DTOs",
            "## Deferred external skills: explicit approval required",
            "docker-compose-patterns",
            "kubernetes-specialist",
            "democratic-csi",
            "Vaultwarden",
            "Do not duplicate the service catalog",
        ),
    ),
    ".agents/skills/docker-compose-orchestration/SKILL.md": (
        "## Precedence over external Docker Compose skills",
        (
            "AGENTS.md",
            "docker-compose-patterns",
            "TrueNAS-managed ZFS datasets",
            "/mnt/cpool/<service>/",
            "/mnt/cpool/secrets/runtime/<service>/",
            "Vaultwarden",
            "shared networks",
            "never treat",
        ),
    ),
    ".agents/skills/nabla-service-catalog/SKILL.md": (
        "## Backstage catalog authority with external skills",
        (
            "AGENTS.md",
            "Backstage",
            "entityRef",
            "catalogRevision",
            "democratic-csi",
            "unknown",
        ),
    ),
    ".agents/skills/homelab-secrets/SKILL.md": (
        None,
        ("Vaultwarden", "/mnt/cpool/secrets/runtime", ".env.compose"),
    ),
    ".agents/skills/local-first-quality/SKILL.md": (
        "## Skills externes : contrôle local avant installation",
        (
            "AGENTS.md",
            "docs/agent-skills-architecture.md",
            "accord explicite",
            "agent-skills-check",
        ),
    ),
    "docs/roadmap.md": (
        "## P0 — Agent skill precedence and Compose/FastAPI/Site convergence (2026-10-24)",
        (
            "Ask the user",
            "docker-compose-patterns",
            "kubernetes-specialist",
            "Talos",
            "democratic-csi",
            "entityRef",
            "catalogRevision",
        ),
    ),
    # Keep all supported agent entry files routed through the same policy.
    "CLAUDE.md": (None, ("AGENTS.md",)),
    ".claude/CLAUDE.md": (None, ("AGENTS.md",)),
    ".github/copilot-instructions.md": (None, ("AGENTS.md",)),
    "agent.md": (None, ("AGENTS.md",)),
    "scripts/agent-quality-gate.sh": (
        None,
        (
            "Nabla agent skill precedence is intact",
            "scripts/quality/check-agent-skill-precedence.py",
            "scripts/quality/check-site-catalog-convergence.py",
        ),
    ),
    "justfile": (
        None,
        ("agent-skills-check:", "check-agent-skill-precedence.py"),
    ),
}


def _section(source: str, heading: str | None) -> str:
    if heading is None:
        return source
    lines = source.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        return ""
    for end in range(start + 1, len(lines)):
        if lines[end].startswith("## "):
            return "\n".join(lines[start:end])
    return "\n".join(lines[start:])


def audit(root: Path) -> list[str]:
    """Return bounded explanations; no mutation or third-party command calls."""
    issues: list[str] = []
    for relative, (heading, required) in REQUIRED.items():
        path = root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            issues.append(f"{relative}: missing or unreadable policy file")
            continue
        scoped = _section(content, heading)
        if heading and not scoped:
            issues.append(f"{relative}: missing section: {heading}")
            continue
        for marker in required:
            if marker not in scoped:
                issues.append(f"{relative}: missing policy marker: {marker}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    issues = audit(args.root)
    if issues:
        for issue in issues:
            print("FAIL " + issue, file=sys.stderr)
        return 1
    print(f"PASS agent skill precedence: {len(REQUIRED)} policy sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
