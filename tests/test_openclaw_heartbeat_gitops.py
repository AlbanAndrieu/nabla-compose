"""Offline regression tests for heartbeat GitOps policy and backup."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-heartbeat-gitops.py"
spec = importlib.util.spec_from_file_location("openclaw_heartbeat_gitops", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_backup_then_apply_and_check(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# comments only\n")
    workspace = tmp_path / "state/workspace"
    workspace.mkdir(parents=True)
    target = workspace / "HEARTBEAT.md"
    target.write_text("old private data\n")
    assert mod.operate("check", tmp_path / "state", source).startswith("different")
    assert "backup=" in mod.operate("backup", tmp_path / "state", source)
    assert "applied_sha256=" in mod.operate("apply", tmp_path / "state", source)
    assert mod.operate("check", tmp_path / "state", source).startswith("matching")
    assert target.stat().st_mode & 0o777 == 0o600
    backups = list((tmp_path / "state/backups/heartbeat-gitops").glob("HEARTBEAT.*.md"))
    assert backups and backups[0].read_text() == "old private data\n"


def test_rejects_symlink(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# safe\n")
    workspace = tmp_path / "state/workspace"
    workspace.mkdir(parents=True)
    (workspace / "HEARTBEAT.md").symlink_to(source)
    try:
        mod.operate("backup", tmp_path / "state", source)
    except ValueError as exc:
        assert str(exc) == "symlink_refused"
    else:
        raise AssertionError("symlink must be refused")


def test_refuses_missing_heartbeat(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# safe\n")
    (tmp_path / "state/workspace").mkdir(parents=True)
    try:
        mod.operate("apply", tmp_path / "state", source)
    except ValueError as exc:
        assert str(exc) == "current_heartbeat_missing_refuse_unsafe_replace"
    else:
        raise AssertionError("missing heartbeat must be refused")

def test_repeated_backup_does_not_fail_in_same_second(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("# safe\n")
    workspace = tmp_path / "state/workspace"
    workspace.mkdir(parents=True)
    (workspace / "HEARTBEAT.md").write_text("previous\n")
    first = mod.operate("backup", tmp_path / "state", source)
    second = mod.operate("backup", tmp_path / "state", source)
    assert first == second
    assert len(list((tmp_path / "state/backups/heartbeat-gitops").glob("HEARTBEAT.*.md"))) == 1
