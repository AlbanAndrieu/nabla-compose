"""Offline contracts for scripts/truenas/reconcile-custom-apps.py."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-custom-apps.py"
MANIFEST = ROOT / "config/truenas/custom-apps.yml"
ACK = "I_ACCEPT_TRUENAS_CUSTOM_APP_RECONCILE"
CANON = "/mnt/cpool/compose/nabla-compose"

_spec = importlib.util.spec_from_file_location("reconcile_custom_apps", SCRIPT)
module = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(module)


def _compose(repo: Path, name: str, status: str = "", volumes: bool = False) -> None:
    lines = ["services:", f"  {name}:", "    image: example/app:1.0",
             f"    container_name: {name}", "    x-nabla:", f"      id: {name}",
             "      runtime:", "        provider: truenas-app",
             f"        containerService: {name}"]
    if status:
        lines.append(f"      status: {status}")
    if volumes:
        lines += ["volumes:", "  data: {}"]
    path = repo / "apps" / name / "compose.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _entry(name: str, state: str = "running") -> dict:
    return {"name": name, "include": [f"apps/{name}/compose.yml"], "state": state}


def _fixture(tmp: Path) -> dict[str, Path]:
    repo = tmp / "repo"
    for name in ("alpha", "bravo", "charlie", "delta", "echo", "golf", "juliet", "lima", "india"):
        _compose(repo, name)
    _compose(repo, "foxtrot", volumes=True)
    manifest = {"version": 1, "canonical_root": CANON, "catalog_native": ["delta"], "apps": [
        _entry("alpha"), _entry("bravo"), _entry("charlie", "stopped"), _entry("delta"),
        _entry("echo"), _entry("foxtrot"), _entry("golf"), _entry("juliet"),
        _entry("lima", "stopped"), _entry("mike"),
    ]}
    paths = {"repo": repo, "manifest": tmp / "custom-apps.yml", "apps": tmp / "apps.json",
             "configs": tmp / "configs.json", "containers": tmp / "containers.json"}
    paths["manifest"].write_text(module.render_manifest(manifest), encoding="utf-8")
    paths["apps"].write_text(json.dumps([
        {"id": "bravo", "state": "STOPPED", "custom_app": True},
        {"id": "charlie", "state": "RUNNING", "custom_app": True},
        {"id": "delta", "state": "RUNNING", "custom_app": False},
        {"id": "hotel", "state": "RUNNING", "custom_app": True},
        {"id": "juliet", "state": "RUNNING", "custom_app": True},
    ]))
    paths["configs"].write_text(json.dumps({
        "bravo": {"include": [f"{CANON}/apps/bravo/compose.yml"]},
        "charlie": {"include": [f"{CANON}/apps/charlie/compose.yml"]},
        "hotel": {"include": [f"{CANON}/apps/hotel/compose.yml"]},
        "juliet": {"include": ["/mnt/cpool/compose/old/juliet.yml"]},
    }))
    paths["containers"].write_text(json.dumps([
        {"name": "echo", "project": "nabla-compose"},
        {"name": "foxtrot", "project": "foxtrot"},
        {"name": "golf", "project": "ix-hotel"},
    ]))
    return paths


def _run(paths: dict, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(paths["repo"]),
         "--manifest", str(paths["manifest"]), "--apps-json", str(paths["apps"]),
         "--configs-json", str(paths["configs"]), "--containers-json", str(paths["containers"]),
         *extra],
        capture_output=True, text=True, check=False)


def _rows(stdout: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and not line.startswith("plan_hash"):
            key = parts[1] if parts[1] != "-" else parts[3]
            rows[key] = (parts[0], parts[2])
    return rows


def _hash(stdout: str) -> str:
    return next(l.split()[0].split("=")[1] for l in stdout.splitlines() if l.startswith("plan_hash="))


def test_check_classifies_manifest_repository_and_live_state(tmp_path: Path) -> None:
    result = _run(_fixture(tmp_path))
    assert result.returncode == 0, result.stderr
    rows = _rows(result.stdout)
    assert rows["alpha"] == ("MISSING", "create")
    assert rows["bravo"] == ("STOPPED", "start")
    assert rows["charlie"] == ("RUNNING_BUT_DESIRED_STOPPED", "-")
    assert rows["delta"] == ("CATALOG_NATIVE", "-")
    assert rows["echo"] == ("ORPHAN_OUTSIDE_UI", "adopt")
    assert rows["foxtrot"] == ("ORPHAN_NAMED_VOLUMES", "-")
    assert rows["golf"] == ("CONFLICT_OTHER_APP", "-")
    assert rows["juliet"] == ("INCLUDE_DRIFT", "update")
    assert rows["lima"] == ("MISSING", "create")
    assert rows["mike"] == ("MISSING_COMPOSE_FILE", "-")
    assert rows["hotel"] == ("UNMANAGED_LIVE", "-")
    assert rows["apps/india/compose.yml"] == ("NEW_IN_REPO", "-")


def test_apply_requires_plan_hash_and_acknowledgement(tmp_path: Path) -> None:
    result = _run(_fixture(tmp_path), "--apply", "--expected-plan-hash", "0" * 16,
                  "--acknowledge", ACK)
    assert result.returncode == 2 and "REFUSED" in result.stdout


FAKE_MIDCLT = '''#!{python}
import json, sys
from pathlib import Path
state_file, log = Path({state!r}), Path({log!r})
args = sys.argv[1:]
with log.open("a") as handle:
    handle.write(json.dumps(args) + "\\n")
state = json.loads(state_file.read_text())
method = next(a for a in args if a.startswith("app."))
rest = args[args.index(method) + 1:]
if method == "app.query":
    print(json.dumps([{{"id": k, "state": v, "custom_app": True}} for k, v in state.items()]))
elif method == "app.create":
    state[json.loads(rest[0])["app_name"]] = "RUNNING"
elif method in ("app.start", "app.update"):
    state[rest[0]] = "RUNNING"
elif method == "app.stop":
    state[rest[0]] = "STOPPED"
state_file.write_text(json.dumps(state))
'''


def _fake(tmp: Path, mem_gib: int) -> tuple[Path, list[str]]:
    state, log = tmp / "state.json", tmp / "calls.log"
    state.write_text(json.dumps({"bravo": "STOPPED", "juliet": "RUNNING"}))
    midclt = tmp / "midclt"
    midclt.write_text(FAKE_MIDCLT.format(python=sys.executable, state=str(state), log=str(log)))
    docker = tmp / "docker"
    docker.write_text(f"#!/bin/sh\necho docker \"$*\" >> {tmp / 'docker.log'}\n")
    for path in (midclt, docker):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    meminfo = tmp / "meminfo"
    meminfo.write_text(f"MemTotal: 65011712 kB\nMemAvailable: {mem_gib * 2**20} kB\n")
    return log, ["--midclt", str(midclt), "--docker", str(docker), "--meminfo", str(meminfo),
                 "--timeout", "30"]


def test_apply_recreates_updates_starts_and_keeps_stopped_apps_stopped(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    log, fake = _fake(tmp_path, mem_gib=20)
    digest = _hash(_run(paths).stdout)
    result = _run(paths, "--apply", "--expected-plan-hash", digest, "--acknowledge", ACK, *fake)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    creates = {json.loads(c[-1])["app_name"]: json.loads(c[-1]) for c in calls if "app.create" in c}
    assert set(creates) == {"alpha", "lima"}
    assert creates["alpha"]["custom_app"] is True
    assert creates["alpha"]["custom_compose_config_string"] == (
        f"include:\n  - {CANON}/apps/alpha/compose.yml\n")
    update = next(c for c in calls if "app.update" in c)
    assert json.loads(update[-1]) == {"custom_compose_config": {"include": [f"{CANON}/apps/juliet/compose.yml"]}}
    assert ["call", "-j", "app.start", "bravo"] in calls
    assert ["call", "-j", "app.stop", "lima"] in calls  # created, then kept stopped
    assert not (tmp_path / "docker.log").exists()  # echo needs --adopt
    assert "SKIP: echo" in result.stdout


def test_apply_stops_below_memory_floor(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    log, fake = _fake(tmp_path, mem_gib=2)
    digest = _hash(_run(paths).stdout)
    result = _run(paths, "--apply", "--expected-plan-hash", digest, "--acknowledge", ACK, *fake)
    assert result.returncode == 3
    assert not log.exists() or "app.create" not in log.read_text()


def test_capture_writes_manifest_from_live_custom_apps(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    configs = json.loads(paths["configs"].read_text())
    configs["zulu"] = {"services": {"zulu": {"image": "x"}}}
    configs["yankee"] = {"include": ["/srv/elsewhere/compose.yml"]}
    paths["configs"].write_text(json.dumps(configs))
    apps = json.loads(paths["apps"].read_text()) + [
        {"id": "zulu", "state": "RUNNING", "custom_app": True},
        {"id": "yankee", "state": "RUNNING", "custom_app": True},
        {"id": "kilo", "state": "STOPPED", "custom_app": False},
    ]
    paths["apps"].write_text(json.dumps(apps))
    result = _run(paths, "--capture", "--write")
    assert result.returncode == 0, result.stderr
    saved = yaml.safe_load(paths["manifest"].read_text())
    by_name = {e["name"]: e for e in saved["apps"]}
    assert by_name["hotel"]["include"] == ["apps/hotel/compose.yml"]  # unmanaged -> added
    assert by_name["juliet"]["include"] == ["apps/juliet/compose.yml"] or "OUTSIDE_REPO juliet" in result.stdout
    assert by_name["zulu"].get("inline") is True
    assert "yankee" not in by_name and "OUTSIDE_REPO yankee" in result.stdout
    assert "kilo" in saved["catalog_native"]
    assert by_name["alpha"]["state"] == "running"  # not live: kept for recreation
    assert by_name["charlie"]["state"] == "stopped"  # manifest intent preserved


# ---- contracts on the committed manifest -----------------------------------
def test_committed_manifest_is_valid_and_rendered_canonically() -> None:
    manifest = module.load_manifest(MANIFEST)
    assert MANIFEST.read_text(encoding="utf-8") == module.render_manifest(manifest)
    assert manifest["canonical_root"] == CANON
    names = {e["name"] for e in manifest["apps"]}
    assert not names & set(manifest["catalog_native"])


def test_committed_manifest_includes_exist_and_are_active() -> None:
    manifest = module.load_manifest(MANIFEST)
    for entry in manifest["apps"]:
        for rel in entry.get("include") or []:
            facts = module.compose_facts(ROOT, rel)
            assert facts is not None, f"{entry['name']}: missing {rel}"
            if entry.get("state") == "running":
                assert facts["statuses"] in ([], ["active"]), f"{entry['name']}: {facts['statuses']}"


def test_every_active_repository_app_is_declared() -> None:
    manifest = module.load_manifest(MANIFEST)
    assert module.new_in_repo(ROOT, manifest, module._planner()) == [], (
        "add new apps/<dir>/compose.yml to config/truenas/custom-apps.yml")


def test_manifest_matches_runtime_shapes() -> None:
    assert module.live_includes({"include": ["/a.yml", {"path": "/b.yml"}]}) == ["/a.yml", "/b.yml"]
    assert module.live_includes({"services": {}}) is None
    assert os.access(SCRIPT, os.X_OK)
