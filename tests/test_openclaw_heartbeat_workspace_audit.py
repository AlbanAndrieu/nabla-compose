"""Hermetic tests for the read-only heartbeat file audit."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/workstation/openclaw-heartbeat-workspace-audit.py"
spec = importlib.util.spec_from_file_location("heartbeat_workspace_audit", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_detects_distinct_workspace_files_without_exposing_content(tmp_path):
    main = tmp_path / "workspace/HEARTBEAT.md"
    cron = tmp_path / "workspace/cron/HEARTBEAT.md"
    main.parent.mkdir(parents=True)
    cron.parent.mkdir(parents=True)
    main.write_text("PRIVATE HEARTBEAT CONTENT\n")
    cron.write_text("cron only\n")
    result = module.inspect(tmp_path)
    assert result["active_workspace"] == "not_determined"
    assert result["files"][0]["sha256"] != result["files"][1]["sha256"]
    assert "PRIVATE" not in str(result)


def test_refuses_symlink_and_handles_missing_files(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace/HEARTBEAT.md").symlink_to("/etc/passwd")
    result = module.inspect(tmp_path)
    assert result["files"][0]["status"] == "symlink_refused"
    assert result["files"][1]["status"] == "absent"
