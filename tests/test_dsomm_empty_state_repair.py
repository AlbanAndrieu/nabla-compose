"""Regression tests for fail-closed DSOMM empty-state repair."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/repair-empty-dsomm-assessment.py"
spec = importlib.util.spec_from_file_location("repair_empty_dsomm", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def test_repairs_only_empty_documents(tmp_path: Path) -> None:
    (tmp_path / "team-progress.yaml").write_text("progress: {}\n")
    (tmp_path / "team-evidence.yaml").write_text("evidence: {}\n")
    assert module.run(tmp_path, False) == 0
    assert module.run(tmp_path, True) == 0
    assert "066084c6" in (tmp_path / "team-progress.yaml").read_text()
    backups = list(tmp_path.glob("backup-empty-assessment-*"))
    assert len(backups) == 1
    assert (backups[0] / "team-progress.yaml").read_text() == "progress: {}\n"


def test_rejects_nonempty_without_changing_any_file(tmp_path: Path) -> None:
    progress = tmp_path / "team-progress.yaml"
    progress.write_text("progress:\n  existing: {Nabla Platform: {Started: '2026-10-01'}}\n")
    evidence = tmp_path / "team-evidence.yaml"
    evidence.write_text("evidence: {}\n")
    with pytest.raises(ValueError, match="not a recognized empty"):
        module.run(tmp_path, True)
    assert "existing" in progress.read_text()
    assert evidence.read_text() == "evidence: {}\n"
    assert not list(tmp_path.glob("backup-empty-assessment-*"))


def test_rejects_unexpected_empty_yaml_structure(tmp_path: Path) -> None:
    progress = tmp_path / "team-progress.yaml"
    progress.write_text("progress: []\n")
    evidence = tmp_path / "team-evidence.yaml"
    evidence.write_text("evidence: {}\n")
    with pytest.raises(ValueError, match="not a recognized empty"):
        module.run(tmp_path, False)
