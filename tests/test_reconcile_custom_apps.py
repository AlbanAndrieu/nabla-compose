"""Offline contracts for scripts/truenas/reconcile-custom-apps.py."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-custom-apps.py"
ACK = "I_ACCEPT_TRUENAS_CUSTOM_APP_RECONCILE"


def _compose(repo: Path, name: str, body: str) -> None:
    path = repo / "apps" / name / "compose.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _service(name: str, status: str = "", app_id: str = "", extra: str = "") -> str:
    lines = [
        "services:", f"  {name}:", "    image: example/app:1.0",
        f"    container_name: {name}", "    x-nabla:", f"      id: {name}",
        "      runtime:", "        provider: truenas-app",
        f"        containerService: {name}",
    ]
    if app_id:
        lines.append(f"        appId: {app_id}")
    if status:
        lines.append(f"      status: {status}")
    return "\n".join(lines) + "\n" + extra


def _repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    _compose(repo, "alpha", _service("alpha"))
    _compose(repo, "bravo", _service("bravo"))
    _compose(repo, "charlie", _service("charlie", status="planned"))
    _compose(repo, "delta", _service("delta", app_id="delta-native"))
    _compose(repo, "echo", _service("echo"))
    _compose(repo, "foxtrot", _service("foxtrot", extra="volumes:\n  data: {}\n"))
    _compose(repo, "golf", _service("golf"))
    return repo


def _snapshots(tmp: Path) -> tuple[Path, Path]:
    apps = tmp / "apps.json"
    apps.write_text(json.dumps([
        {"id": "bravo", "state": "STOPPED", "custom_app": True},
        {"id": "delta-native", "state": "RUNNING", "custom_app": False},
        {"id": "hotel", "state": "RUNNING", "custom_app": True},
    ]))
    containers = tmp / "containers.json"
    containers.write_text(json.dumps([
        {"name": "echo", "project": "nabla-compose"},
        {"name": "foxtrot", "project": "foxtrot"},
        {"name": "golf", "project": "ix-hotel"},
    ]))
    return apps, containers


def _run(tmp: Path, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
    apps, containers = _snapshots(tmp)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(_repo(tmp)),
         "--apps-json", str(apps), "--containers-json", str(containers), *extra],
        capture_output=True, text=True, check=False, env={**os.environ, **(env or {})},
    )


def _verdicts(stdout: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3].startswith("apps/"):
            rows[parts[3].split("/")[1]] = (parts[0], parts[2])
    return rows


def test_check_classifies_every_repository_app(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    rows = _verdicts(result.stdout)
    assert rows["alpha"] == ("MISSING", "create")
    assert rows["bravo"] == ("STOPPED", "start")
    assert rows["charlie"] == ("DECLARED_INACTIVE", "-")
    assert rows["delta"] == ("CATALOG_NATIVE", "-")
    assert rows["echo"] == ("ORPHAN_OUTSIDE_UI", "adopt")
    assert rows["foxtrot"] == ("ORPHAN_NAMED_VOLUMES", "-")
    assert rows["golf"] == ("CONFLICT_OTHER_APP", "-")
    assert "plan_hash=" in result.stdout


def test_apply_requires_plan_hash_and_acknowledgement(tmp_path: Path) -> None:
    result = _run(tmp_path, "--apply", "--expected-plan-hash", "0" * 16, "--acknowledge", ACK)
    assert result.returncode == 2
    assert "REFUSED" in result.stdout


def _fake_bins(tmp: Path) -> tuple[Path, Path, Path]:
    log = tmp / "calls.log"
    midclt = tmp / "midclt"
    midclt.write_text(
        "#!/bin/sh\n"
        f'echo "midclt $*" >> "{log}"\n'
        'if [ "$2" = "app.query" ]; then\n'
        '  echo \'[{"id":"alpha","state":"RUNNING","custom_app":true},'
        '{"id":"bravo","state":"RUNNING","custom_app":true},'
        '{"id":"echo","state":"RUNNING","custom_app":true}]\'\n'
        "fi\n"
    )
    docker = tmp / "docker"
    docker.write_text(f'#!/bin/sh\necho "docker $*" >> "{log}"\n')
    for path in (midclt, docker):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return log, midclt, docker


def _meminfo(tmp: Path, gib: int) -> Path:
    path = tmp / "meminfo"
    path.write_text(f"MemTotal: 65011712 kB\nMemAvailable: {gib * 2**20} kB\n")
    return path


def _plan_hash(tmp: Path) -> str:
    out = _run(tmp).stdout
    return next(l.split()[0].split("=")[1] for l in out.splitlines() if l.startswith("plan_hash="))


def test_apply_creates_include_wrapper_and_starts_without_adopting(tmp_path: Path) -> None:
    log, midclt, docker = _fake_bins(tmp_path)
    digest = _plan_hash(tmp_path)
    result = _run(tmp_path, "--apply", "--expected-plan-hash", digest, "--acknowledge", ACK,
                  "--midclt", str(midclt), "--docker", str(docker),
                  "--meminfo", str(_meminfo(tmp_path, 20)))
    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text()
    assert "app.create" in calls and '"app_name": "alpha"' in calls
    assert "include:" in calls
    assert "- /mnt/cpool/compose/nabla-compose/apps/alpha/compose.yml" in calls
    assert "app.start bravo" in calls
    assert "docker" not in calls  # echo runs outside the UI: skipped without --adopt
    assert "SKIP: echo" in result.stdout


def test_apply_stops_below_memory_floor(tmp_path: Path) -> None:
    log, midclt, docker = _fake_bins(tmp_path)
    digest = _plan_hash(tmp_path)
    result = _run(tmp_path, "--apply", "--expected-plan-hash", digest, "--acknowledge", ACK,
                  "--midclt", str(midclt), "--docker", str(docker),
                  "--meminfo", str(_meminfo(tmp_path, 2)))
    assert result.returncode == 3
    assert not log.exists() or "app.create" not in log.read_text()
