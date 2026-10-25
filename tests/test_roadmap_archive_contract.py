"""Offline contracts for current roadmap, immutable archive and navigation.

Never access GitHub, production hosts, secrets or shell state.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/archive/roadmap-through-2026-10-24.md"
ORIGINAL_GIT_BLOB_SHA = "d429d33b46585ca4de10e347960667810985954e"
CHECK_LINKS = (
    "README.md",
    "docs/roadmap.md",
    "docs/runbooks/README.md",
    "docs/runbooks/homelab-runtime-acceptance.md",
    "docs/runbooks/homelab-refactoring-risk-register.md",
)


def test_archive_is_byte_for_byte_identical_to_reviewed_source() -> None:
    data = ARCHIVE.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    git_blob = hashlib.sha1(header + data, usedforsecurity=False).hexdigest()
    assert git_blob == ORIGINAL_GIT_BLOB_SHA
    assert len(data.splitlines()) > 3000


def test_active_roadmap_has_a_bounded_current_scope() -> None:
    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    assert len(roadmap.splitlines()) < 300
    assert "## P0 — Terminer la stabilisation réelle" in roadmap
    assert "## P1 — Dette de code et de documentation" in roadmap
    assert "archive/roadmap-through-2026-10-24.md" in roadmap
    assert "NOT_VERIFIED" in roadmap
    assert "ACCEPTED (runtime)" in roadmap


def test_documentation_relative_links_resolve_inside_repository() -> None:
    markdown_link = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    for relative in CHECK_LINKS:
        page = ROOT / relative
        source = page.read_text(encoding="utf-8")
        for link in markdown_link.findall(source):
            target = link.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (page.parent / target).resolve()
            assert resolved.is_relative_to(ROOT), (relative, link)
            assert resolved.is_file(), (relative, link)
