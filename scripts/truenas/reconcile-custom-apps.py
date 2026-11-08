#!/usr/bin/env python3
"""Recreate and reconcile the TrueNAS Custom Apps declared in the repository.

``config/truenas/custom-apps.yml`` lists every Custom App owned by this
repository: its name, the Compose files it includes and its desired state.
Each App is (re)created exactly like an App added through the UI: a Custom App
whose Compose is an include wrapper (``include: [<canonical_root>/<file>]``),
so it is visible and managed by TrueNAS. The manifest is enough to rebuild all
Custom Apps if they disappear, and to create missing or new ones.

Modes (``--check`` is the default and read-only):
  --check    compare the manifest, the repository and the live NAS; print a plan
  --apply    create missing Apps, fix include drift, start stopped Apps in
             lifecycle order; needs the plan hash and --acknowledge; stops at
             the first failure or when MemAvailable drops below a floor
  --capture  read live Custom Apps (names, include paths, native Apps) and show
             the manifest they imply; --write saves it for review and commit

Native catalog Apps, inline (non-include) Compose and containers owned by
another App are never touched. Containers started outside TrueNAS are only
replaced with --adopt. Environment values are never read or printed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "scripts/truenas/plan-app-lifecycle-order.py"
MANIFEST = ROOT / "config/truenas/custom-apps.yml"
ACK = "I_ACCEPT_TRUENAS_CUSTOM_APP_RECONCILE"
APP_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STATES = ("running", "stopped")
HEADER = """---
# TrueNAS Custom Apps owned by this repository (scripts/truenas/reconcile-custom-apps.py).
# Each entry is recreated exactly like an App added through the UI: a Custom App
# whose Compose is an include wrapper pointing at canonical_root/<include>.
# Seeded from apps/*/compose.yml on 2026-11-07; confirm names/includes against
# the live NAS with `reconcile-custom-apps.py --capture` and commit the diff.
# state: running (create/start) or stopped (create, never started by --apply).
# New Compose Apps must be added here (tests/test_reconcile_custom_apps.py).
"""
NATIVE_HEADER = """# Native TrueNAS catalog Apps (custom_app=false, inventory 2026-11-05). Never
# created by the reconciler; migrate them with
# docs/runbooks/2026-11-06-catalog-apps-to-compose.md, then move them to apps.
"""


def _planner():
    spec = importlib.util.spec_from_file_location("lifecycle_planner", PLANNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- manifest --
def load_manifest(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seen = set()
    for entry in data.get("apps") or []:
        name = entry.get("name", "")
        if not APP_NAME.match(name) or name in seen:
            raise ValueError(f"invalid or duplicate App name: {name!r}")
        seen.add(name)
        if entry.get("inline"):
            continue
        if entry.get("state", "running") not in STATES:
            raise ValueError(f"{name}: state must be one of {STATES}")
        includes = entry.get("include") or []
        if not includes or any(Path(p).is_absolute() or ".." in Path(p).parts for p in includes):
            raise ValueError(f"{name}: include must list repository-relative paths")
    return data


def _scalar(value: str) -> str:
    """Plain YAML scalar when it round-trips, JSON-quoted otherwise."""
    try:
        if yaml.safe_load(f"k: {value}") == {"k": value}:
            return value
    except yaml.YAMLError:
        pass
    return json.dumps(value)


def render_manifest(data: dict) -> str:
    out = [HEADER.rstrip("\n"), f"version: {data.get('version', 1)}",
           f"canonical_root: {data['canonical_root']}", "apps:"]
    for entry in sorted(data.get("apps") or [], key=lambda e: e["name"]):
        out.append(f"  - name: {entry['name']}")
        if entry.get("inline"):
            out.append("    inline: true")
        else:
            out.append("    include:")
            out += [f"      - {p}" for p in entry["include"]]
            out.append(f"    state: {entry.get('state', 'running')}")
        for key in ("reason", "note"):
            if entry.get(key):
                out.append(f"    {key}: {_scalar(str(entry[key]))}")
    out.append(NATIVE_HEADER.rstrip("\n"))
    out.append("catalog_native:")
    out += [f"  - {n}" for n in sorted(data.get("catalog_native") or [])]
    return "\n".join(out) + "\n"


# -------------------------------------------------------------- repository --
def compose_facts(repo: Path, rel: str) -> dict | None:
    path = repo / rel
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = data.get("services") or {}
    declared = [svc["x-nabla"] for svc in services.values()
                if isinstance(svc, dict)
                and ((svc.get("x-nabla") or {}).get("runtime") or {}).get("provider") == "truenas-app"]
    return {
        "containers": sorted(str(s["container_name"]) for s in services.values()
                             if isinstance(s, dict) and s.get("container_name")),
        "named_volumes": sorted(n for n, v in (data.get("volumes") or {}).items()
                                if not (isinstance(v, dict) and v.get("external"))),
        "app_ids": sorted({str(x["runtime"]["appId"]) for x in declared if x["runtime"].get("appId")}),
        "statuses": sorted({str(x.get("status") or "active") for x in declared}),
        "truenas": bool(declared),
    }


def new_in_repo(repo: Path, manifest: dict, planner) -> list[str]:
    """Active TrueNAS Compose files neither in the manifest nor a native App."""
    referenced = {p for e in manifest.get("apps") or [] for p in e.get("include") or []}
    native = set(manifest.get("catalog_native") or [])
    missing = []
    for compose in sorted((repo / "apps").glob("*/compose.yml")):
        rel = f"apps/{compose.parent.name}/compose.yml"
        facts = compose_facts(repo, rel)
        if not facts or not facts["truenas"] or rel in referenced or facts["statuses"] != ["active"]:
            continue
        wanted = facts["app_ids"][0] if len(facts["app_ids"]) == 1 else compose.parent.name
        if not planner.resolve_known_app(wanted, native):
            missing.append(rel)
    return missing


# --------------------------------------------------------------- live state --
def live_includes(config) -> list[str] | None:
    """Include paths of a Custom App config; None when not an include wrapper."""
    if not isinstance(config, dict) or not isinstance(config.get("include"), list):
        return None
    paths: list[str] = []
    for item in config["include"]:
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict):
            value = item.get("path")
            paths.extend(value if isinstance(value, list) else [value] if value else [])
    return paths


def classify(manifest, repo, apps, configs, containers, planner) -> list[dict]:
    root = manifest["canonical_root"]
    live = {str(a["id"]): a for a in apps}
    native_live = {i for i, a in live.items() if not a.get("custom_app", True)}
    rows = []
    for entry in manifest.get("apps") or []:
        name = entry["name"]
        row = {"app": name, "include": entry.get("include"), "state_wanted": entry.get("state", "running")}
        if entry.get("inline"):
            rows.append({**row, "verdict": "INLINE_NOT_RECREATABLE", "action": None})
            continue
        expected = [f"{root}/{p}" for p in entry["include"]]
        row["paths"] = expected
        if planner.resolve_known_app(name, native_live):
            rows.append({**row, "verdict": "CATALOG_NATIVE", "action": None})
            continue
        state = live.get(name, {}).get("state")
        if state:
            drift = configs.get(name)
            if drift is not None and sorted(drift) != sorted(expected):
                rows.append({**row, "verdict": "INCLUDE_DRIFT", "action": "update", "live": drift})
            elif row["state_wanted"] == "running" and state in ("STOPPED", "CRASHED"):
                rows.append({**row, "verdict": state, "action": "start"})
            elif row["state_wanted"] == "stopped" and state == "RUNNING":
                rows.append({**row, "verdict": "RUNNING_BUT_DESIRED_STOPPED", "action": None})
            else:
                rows.append({**row, "verdict": state, "action": None})
            continue
        facts = [compose_facts(repo, p) for p in entry["include"]]
        if any(f is None for f in facts):
            rows.append({**row, "verdict": "MISSING_COMPOSE_FILE", "action": None})
            continue
        names = {c for f in facts for c in f["containers"]}
        volumes = sorted({v for f in facts for v in f["named_volumes"]})
        elsewhere = sorted(c["name"] for c in containers if c["name"] in names
                           and c["project"].startswith("ix-") and c["project"] != f"ix-{name}")
        orphans = sorted(c["name"] for c in containers if c["name"] in names
                         and not c["project"].startswith("ix-"))
        if elsewhere:
            rows.append({**row, "verdict": "CONFLICT_OTHER_APP", "action": None, "orphans": elsewhere})
        elif orphans:
            rows.append({**row, "orphans": orphans,
                         "verdict": "ORPHAN_NAMED_VOLUMES" if volumes else "ORPHAN_OUTSIDE_UI",
                         "action": None if volumes else "adopt"})
        else:
            rows.append({**row, "verdict": "MISSING", "action": "create"})
    declared = {e["name"] for e in manifest.get("apps") or []}
    for app_id, app in sorted(live.items()):
        if app.get("custom_app", True) and app_id not in declared:
            rows.append({"app": app_id, "verdict": "UNMANAGED_LIVE", "action": None})
    for rel in new_in_repo(repo, manifest, planner):
        rows.append({"app": None, "include": [rel], "verdict": "NEW_IN_REPO", "action": None})
    return rows


def capture(manifest, apps, configs) -> tuple[dict, list[str]]:
    """Manifest implied by the live NAS; existing states/notes are preserved."""
    root = manifest["canonical_root"].rstrip("/") + "/"
    current = {e["name"]: e for e in manifest.get("apps") or []}
    notes, entries = [], dict(current)
    for app in apps:
        name = str(app["id"])
        if not app.get("custom_app", True):
            continue
        config = configs.get(name, "unreadable")
        paths = live_includes(config) if config != "unreadable" else None
        old = current.get(name, {})
        if paths is None:
            if name not in current:
                entries[name] = {"name": name, "inline": True,
                                 "note": "inline or unreadable Compose, move it to a repository file"}
                notes.append(f"INLINE_OR_UNREADABLE {name}")
            continue
        outside = [p for p in paths if not p.startswith(root)]
        if outside:
            notes.append(f"OUTSIDE_REPO {name}: {', '.join(outside)}")
            continue
        rel = [p[len(root):] for p in paths]
        state = old.get("state") or ("running" if app.get("state") == "RUNNING" else "stopped")
        entries[name] = {**old, "name": name, "include": rel, "state": state}
        entries[name].pop("inline", None)
        if old.get("include") != rel:
            notes.append(f"{'UPDATED' if old else 'ADDED'} {name}: {', '.join(rel)}")
    native = sorted({str(a["id"]) for a in apps if not a.get("custom_app", True)}
                    | set(manifest.get("catalog_native") or []))
    native = [n for n in native if n not in entries]
    return {**manifest, "apps": list(entries.values()), "catalog_native": native}, notes


# ------------------------------------------------------------------ actions --
def order(rows, planner_path: Path = PLANNER) -> list[dict]:
    actions = [r for r in rows if r.get("action")]
    ids = sorted({r["app"] for r in actions})
    rank: dict[str, int] = {}
    if ids:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "apps.json"
            snapshot.write_text(json.dumps([{"id": i, "state": "RUNNING"} for i in ids]))
            result = subprocess.run([sys.executable, str(planner_path), "--apps", str(snapshot)],
                                    capture_output=True, text=True, check=False)
        if result.returncode == 0:
            rank = {a: i for i, a in enumerate(json.loads(result.stdout)["start_order"])}
    return sorted(actions, key=lambda r: (rank.get(r["app"], len(rank)), r["app"]))


def plan_hash(actions) -> str:
    stable = [{k: a.get(k) for k in ("app", "action", "paths", "orphans", "state_wanted")} for a in actions]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[:16]


def mem_available_gib(meminfo: Path) -> float:
    for line in meminfo.read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 2**20
    raise RuntimeError("MemAvailable missing from meminfo")


class Runtime:
    def __init__(self, midclt: str, docker: str):
        self.midclt, self.docker = midclt, docker

    def _run(self, *argv: str) -> str:
        return subprocess.run(argv, capture_output=True, text=True, check=True).stdout

    def _call(self, *args: str):
        return json.loads(self._run(self.midclt, "call", *args) or "null")

    def apps(self) -> list[dict]:
        return self._call("app.query", "[]", json.dumps({"select": ["id", "state", "custom_app"]}))

    def configs(self, apps) -> dict:
        found = {}
        for app in apps:
            if app.get("custom_app", True):
                try:
                    found[app["id"]] = live_includes(self._call("app.config", app["id"]))
                except (subprocess.CalledProcessError, json.JSONDecodeError):
                    found[app["id"]] = None
        return found

    def containers(self) -> list[dict]:
        rows = []
        for line in self._run(self.docker, "ps", "-a", "--format", "{{json .}}").splitlines():
            raw = json.loads(line)
            labels = dict(kv.split("=", 1) for kv in raw.get("Labels", "").split(",") if "=" in kv)
            rows.append({"name": raw["Names"], "project": labels.get("com.docker.compose.project", "")})
        return rows

    def create(self, name: str, paths: list[str]) -> None:
        wrapper = "include:\n" + "".join(f"  - {p}\n" for p in paths)
        self._run(self.midclt, "call", "-j", "app.create", json.dumps(
            {"app_name": name, "custom_app": True, "custom_compose_config_string": wrapper}))

    def update(self, name: str, paths: list[str]) -> None:
        self._run(self.midclt, "call", "-j", "app.update", name,
                  json.dumps({"custom_compose_config": {"include": paths}}))

    def start(self, name: str) -> None:
        self._run(self.midclt, "call", "-j", "app.start", name)

    def stop(self, name: str) -> None:
        self._run(self.midclt, "call", "-j", "app.stop", name)

    def remove_containers(self, names: list[str]) -> None:
        self._run(self.docker, "stop", *names)
        self._run(self.docker, "rm", *names)

    def wait(self, name: str, target: str, timeout: int) -> str:
        deadline, state = time.monotonic() + timeout, "UNKNOWN"
        while time.monotonic() < deadline:
            state = next((a["state"] for a in self.apps() if a["id"] == name), "MISSING")
            if state in (target, "CRASHED", "MISSING"):
                return state
            time.sleep(5)
        return state


def apply(actions, args, runtime: Runtime) -> int:
    for row in actions:
        free = mem_available_gib(args.meminfo)
        if free < args.min_available_gib:
            print(f"STOP: {free:.1f} GiB available < floor {args.min_available_gib} GiB before {row['app']}")
            return 3
        name, paths, action = row["app"], row["paths"], row["action"]
        if action == "adopt" and not args.adopt:
            print(f"SKIP: {name} runs outside the UI; rerun with --adopt to replace it")
            continue
        if action == "adopt":
            runtime.remove_containers(row["orphans"])
        if action in ("create", "adopt"):
            runtime.create(name, paths)
        elif action == "update":
            runtime.update(name, paths)
        else:
            runtime.start(name)
        state = runtime.wait(name, "RUNNING", args.timeout)
        if state == "RUNNING" and row["state_wanted"] == "stopped":
            runtime.stop(name)
            state = runtime.wait(name, "STOPPED", args.timeout)
        ok = state == ("STOPPED" if row["state_wanted"] == "stopped" else "RUNNING")
        print(f"{'OK' if ok else 'FAIL'}: {action} {name} -> {state}")
        if not ok:
            return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only (default)")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--capture", action="store_true", help="manifest implied by the live NAS")
    p.add_argument("--write", action="store_true", help="with --capture: save the manifest")
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--repo-root", type=Path, default=ROOT)
    p.add_argument("--apps-json", type=Path, help="app.query snapshot (offline)")
    p.add_argument("--configs-json", type=Path, help="{app: app.config} snapshot (offline)")
    p.add_argument("--containers-json", type=Path, help="[{name, project}] snapshot (offline)")
    p.add_argument("--expected-plan-hash")
    p.add_argument("--acknowledge", help=f"type {ACK} exactly")
    p.add_argument("--adopt", action="store_true", help="replace containers running outside the UI")
    p.add_argument("--min-available-gib", type=float, default=6.0)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--meminfo", type=Path, default=Path("/proc/meminfo"))
    p.add_argument("--midclt", default=os.environ.get("MIDCLT", "midclt"))
    p.add_argument("--docker", default=os.environ.get("DOCKER", "docker"))
    args = p.parse_args()

    manifest = load_manifest(args.manifest)
    runtime = Runtime(args.midclt, args.docker)
    apps = json.loads(args.apps_json.read_text()) if args.apps_json else runtime.apps()
    raw_configs = (json.loads(args.configs_json.read_text()) if args.configs_json else None)
    if args.capture:
        configs = raw_configs if raw_configs is not None else {
            a["id"]: runtime._call("app.config", a["id"]) for a in apps if a.get("custom_app", True)}
        updated, notes = capture(manifest, apps, configs)
        print("\n".join(notes) or "manifest already matches the live Custom Apps")
        if args.write:
            args.manifest.write_text(render_manifest(updated), encoding="utf-8")
            print(f"wrote {args.manifest}; review and commit the diff")
        return 0
    configs = ({k: live_includes(v) for k, v in raw_configs.items()} if raw_configs is not None
               else runtime.configs(apps) if not args.apps_json else {})
    containers = (json.loads(args.containers_json.read_text())
                  if args.containers_json else runtime.containers())
    rows = classify(manifest, args.repo_root, apps, configs, containers, _planner())
    actions = order(rows)
    digest = plan_hash(actions)
    for row in sorted(rows, key=lambda r: (r.get("action") is None, r["verdict"], r.get("app") or "")):
        target = ",".join(row.get("include") or []) or "-"
        print(f"{row['verdict']:<28} {row.get('app') or '-':<22} {row.get('action') or '-':<7} {target}")
    print(f"plan_hash={digest} actions={len(actions)}")
    if not args.apply:
        return 0
    if args.acknowledge != ACK or args.expected_plan_hash != digest:
        print(f"REFUSED: --apply needs --expected-plan-hash {digest} and --acknowledge {ACK}")
        return 2
    return apply(actions, args, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
