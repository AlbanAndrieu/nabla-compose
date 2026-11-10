"""Production-readiness matrix and the app-ops.sh dispatcher.

The generated report must match the repository, the planned media stack must
have no gap, and app-ops.sh must stay read-only without an explicit approval.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "truenas" / "audit-master-readiness.py"
OPS = ROOT / "scripts" / "truenas" / "app-ops.sh"
MEDIA_APPS = (
    "media-acquisition", "prowlarr", "radarr", "sonarr", "lidarr",
    "bazarr", "recyclarr", "jellyfin", "seerr", "qbittorrent-exporter",
)


def load():
    spec = importlib.util.spec_from_file_location("audit_master_readiness", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_committed_report_is_current() -> None:
    module = load()
    text = module.render(module.rows())
    assert (ROOT / "docs" / "master-readiness.md").read_text(encoding="utf-8") == text


def test_media_stack_is_ready_for_deployment() -> None:
    rows = {row["app"]: row for row in load().rows()}
    for app in MEDIA_APPS:
        assert rows[app]["gaps"] == [], (app, rows[app]["gaps"])
        assert rows[app]["deploy"] == "deploy-media-stack.sh", app


def test_logical_backup_covers_databases_named_in_compose() -> None:
    rows = {row["app"]: row for row in load().rows()}
    for app, database in (("defectdojo", "defectdojo"), ("langfuse", "langfuse"),
                          ("n8n", "n8n"), ("sonarqube", "sonarqube"),
                          ("sentry", "sentry"), ("sample", "fastapisample")):
        assert database in rows[app]["db_backup"], app


def run_ops(*args: str, approved: bool = False, tmp_path: Path) -> subprocess.CompletedProcess:
    calls = tmp_path / "calls"
    for tool in ("zfs", "docker", "midclt"):
        fake = tmp_path / tool
        fake.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{calls}"\necho "[]"\n', encoding="utf-8")
        fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NO_COLOR": "1"}
    env.pop("NABLA_RUNTIME_CHANGE_APPROVED", None)
    if approved:
        env["NABLA_RUNTIME_CHANGE_APPROVED"] = "yes"
    return subprocess.run(["bash", str(OPS), *args], cwd=ROOT, env=env, capture_output=True, text=True)


def mutations(tmp_path: Path) -> list[str]:
    calls = tmp_path / "calls"
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return [line for line in lines if not line.startswith("midclt call app.query")]


def test_app_ops_backup_is_a_plan_without_apply(tmp_path: Path) -> None:
    result = run_ops("backup", "defectdojo", tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "PLAN: zfs snapshot cpool/defectdojo@manual-defectdojo-" in result.stdout
    assert mutations(tmp_path) == []


def test_app_ops_apply_requires_approval_before_any_step(tmp_path: Path) -> None:
    result = run_ops("backup", "defectdojo", "--apply", tmp_path=tmp_path)
    assert result.returncode != 0
    assert "NABLA_RUNTIME_CHANGE_APPROVED=yes" in result.stderr
    assert mutations(tmp_path) == []


def test_app_ops_approved_backup_snapshots_and_dumps_only_the_app(tmp_path: Path) -> None:
    result = run_ops("backup", "defectdojo", "--apply", approved=True, tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    calls = mutations(tmp_path)
    assert calls[0].startswith("zfs snapshot cpool/defectdojo@manual-defectdojo-")
    assert "-e BACKUP_DATABASES=defectdojo -e BACKUP_REQUIRE_ALL=true postgres-backup" in calls[1]
    assert len(calls) == 2


def test_app_ops_skips_datasets_excluded_from_snapshots(tmp_path: Path) -> None:
    result = run_ops("backup", "jellyfin", "--apply", approved=True, tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "skip cpool/jellyfin-cache" in result.stdout
    assert not any("jellyfin-cache@" in call for call in mutations(tmp_path))


def test_app_ops_rejects_unknown_actions_and_path_like_ids(tmp_path: Path) -> None:
    assert run_ops("destroy", "radarr", tmp_path=tmp_path).returncode == 2
    assert run_ops("status", "../radarr", tmp_path=tmp_path).returncode == 1
    script = OPS.read_text(encoding="utf-8")
    for forbidden in ("app.delete", "zfs destroy", "docker pull", "--no-verify", "docker compose up"):
        assert forbidden not in script, forbidden
