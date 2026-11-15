"""Offline contracts for the inter-repository active portfolio."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/quality/check-roadmap-portfolio.py"


def load_module():
    spec = importlib.util.spec_from_file_location("roadmap_portfolio_check", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portfolio_is_valid_without_network() -> None:
    module = load_module()
    entries, issues = module.audit(ROOT)
    assert not issues, issues
    assert len(entries) >= 19
    assert {'H17', 'H18', 'H19'}.issubset({item['id'] for item in entries})
    assert {item["priority"] for item in entries} == {"P0", "P1", "P2"}
    assert all(item["runtime"] != "ACCEPTED" for item in entries)
    assert "## Séquence approuvée — 14 novembre 2026" in (ROOT / "docs/roadmap-portfolio.md").read_text(encoding="utf-8")


def test_duplicate_or_invalid_status_fails_closed(tmp_path: Path) -> None:
    module = load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "roadmap-portfolio.md").write_text(
        "## Backlog arbitrable\n"
        "| H01 | P0 | compose | CODED | GREEN | contrôle |\n"
        "| H01 | P1 | fastapi | CODED | NOT_VERIFIED | contrôle |\n"
        "| H02 | P2 | compose | PLANNED | NOT_VERIFIED | contrôle |\n",
        encoding="utf-8",
    )
    _, issues = module.audit(tmp_path)
    assert any("duplicate" in issue for issue in issues)
    assert any("runtime status" in issue for issue in issues)
    assert any("approved execution" in issue for issue in issues)


def test_cli_json_and_check_are_read_only() -> None:
    for option in ("--check", "--json", "--worklist"):
        result = subprocess.run(
            [sys.executable, str(TOOL), option],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "H01" in result.stdout or "PASS roadmap portfolio:" in result.stdout
        if option == "--worklist":
            import json
            assert [item["id"] for item in json.loads(result.stdout)] == ["H01", "H02", "H04", "H05", "H12", "H13", "H16"]


def test_blank_line_between_work_items_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "roadmap-portfolio.md").write_text(
        "## Backlog arbitrable\n"
        "| ID | Priority | Owner | Code | Runtime | Evidence |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| H01 | P0 | compose | CODED | NOT_VERIFIED | check |\n"
        "\n"
        "| H02 | P1 | fastapi | CODED | NOT_VERIFIED | check |\n"
        "\n## Séquence validée — H02 → H01 → H05\n",
        encoding="utf-8",
    )
    _, issues = module.audit(tmp_path)
    assert any("split by a blank line" in issue for issue in issues)


def test_approved_order_table_rejects_swapped_chantiers(tmp_path: Path) -> None:
    module = load_module()
    docs = tmp_path / "docs"
    docs.mkdir()
    rows = [
        f"| H{n:02d} | {priority} | compose | CODED | NOT_VERIFIED | check |"
        for n, priority in [(1, "P0"), (2, "P0"), (4, "P0"), (5, "P0"),
                            (12, "P1"), (13, "P1"), (16, "P2")]
    ]
    ordered = ["H02", "H01", "H04", "H05", "H12", "H13", "H16"]
    sequence = [
        f"| {index} | **{name} — probe** | test | gate |"
        for index, name in enumerate(ordered, 1)
    ]
    (docs / "roadmap-portfolio.md").write_text(
        "## Backlog arbitrable\n"
        + "\n".join(rows)
        + "\n\n## Séquence approuvée — 14 novembre 2026\n\n"
        + "\n".join(sequence)
        + "\n",
        encoding="utf-8",
    )
    _, issues = module.audit(tmp_path)
    assert any("approved execution table" in issue for issue in issues)
