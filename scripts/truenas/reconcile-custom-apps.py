#!/usr/bin/env python3
"""Register repository Compose Apps as TrueNAS Custom Apps and start stopped ones.

Every ``apps/<dir>/compose.yml`` whose services declare ``x-nabla.runtime.
provider: truenas-app`` must run as a TrueNAS Custom App created from the
include wrapper (``include: [<repo>/apps/<dir>/compose.yml]``), like the Apps
added through the UI, so it is visible and managed by TrueNAS.

``--check`` (default) is read-only and prints a plan with a hash. ``--apply``
needs that hash and ``--acknowledge``; it creates missing Apps, starts stopped
ones in lifecycle order and stops before free memory drops below a floor.
Apps declared ``planned``/``disabled`` and native catalog Apps are never
touched. Containers running outside TrueNAS (plain ``docker compose``) are only
replaced with ``--adopt``. Environment values are never read or printed.
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
CANONICAL_ROOT = "/mnt/cpool/compose/nabla-compose"
ACK = "I_ACCEPT_TRUENAS_CUSTOM_APP_RECONCILE"
APP_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RUNNING, STOPPED = "RUNNING", "STOPPED"


def _planner():
    spec = importlib.util.spec_from_file_location("lifecycle_planner", PLANNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def discover(repo: Path) -> list[dict]:
    """One candidate per Compose file whose services run as TrueNAS Apps."""
    found = []
    for compose in sorted((repo / "apps").glob("*/compose.yml")):
        data = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        services = data.get("services") or {}
        declared = {
            name: svc["x-nabla"]
            for name, svc in services.items()
            if isinstance(svc, dict)
            and ((svc.get("x-nabla") or {}).get("runtime") or {}).get("provider") == "truenas-app"
        }
        if not declared:
            continue
        app_ids = {str(x["runtime"]["appId"]) for x in declared.values() if x["runtime"].get("appId")}
        statuses = {str(x.get("status") or "active") for x in declared.values()}
        named_volumes = [
            name for name, spec in (data.get("volumes") or {}).items()
            if not (isinstance(spec, dict) and spec.get("external"))
        ]
        found.append({
            "dir": compose.parent.name,
            "compose": f"apps/{compose.parent.name}/compose.yml",
            "app_ids": sorted(app_ids),
            "status": next(iter(statuses)) if len(statuses) == 1 else "mixed",
            "containers": sorted(
                str(svc.get("container_name")) for svc in services.values()
                if isinstance(svc, dict) and svc.get("container_name")
            ),
            "named_volumes": sorted(named_volumes),
        })
    return found


def classify(candidates, apps, containers, planner) -> list[dict]:
    live = {str(app["id"]): app for app in apps}
    rows = []
    for item in candidates:
        row = {k: item[k] for k in ("dir", "compose", "status")}
        if len(item["app_ids"]) > 1:
            rows.append({**row, "app": None, "verdict": "AMBIGUOUS_APP_ID", "action": None})
            continue
        wanted = item["app_ids"][0] if item["app_ids"] else item["dir"]
        app_id = planner.resolve_known_app(wanted, set(live)) or wanted
        row["app"] = app_id
        state = live.get(app_id, {}).get("state")
        row["state"] = state or "MISSING"
        if item["status"] != "active":
            verdict = "DECLARED_INACTIVE_BUT_RUNNING" if state == RUNNING else "DECLARED_INACTIVE"
            rows.append({**row, "verdict": verdict, "action": None})
            continue
        if not APP_NAME.match(app_id):
            rows.append({**row, "verdict": "INVALID_APP_NAME", "action": None})
            continue
        if app_id in live and not live[app_id].get("custom_app", True):
            rows.append({**row, "verdict": "CATALOG_NATIVE", "action": None})
            continue
        if app_id in live:
            action = "start" if state in (STOPPED, "CRASHED") else None
            rows.append({**row, "verdict": state or "UNKNOWN", "action": action})
            continue
        owned_elsewhere = sorted(
            c["name"] for c in containers
            if c["project"].startswith("ix-") and c["project"] != f"ix-{app_id}"
            and c["name"] in item["containers"]
        )
        if owned_elsewhere:
            # Same container_name already managed by another TrueNAS App: the
            # App id is probably mis-resolved; creating would duplicate it.
            rows.append({**row, "verdict": "CONFLICT_OTHER_APP", "action": None,
                         "orphans": owned_elsewhere})
            continue
        orphans = sorted(
            c["name"] for c in containers
            if not c["project"].startswith("ix-")
            and (c["name"] in item["containers"] or c["project"] == item["dir"])
        )
        if orphans:
            row.update(orphans=orphans, named_volumes=item["named_volumes"])
            verdict = "ORPHAN_NAMED_VOLUMES" if item["named_volumes"] else "ORPHAN_OUTSIDE_UI"
            rows.append({**row, "verdict": verdict, "action": "adopt" if not item["named_volumes"] else None})
        else:
            rows.append({**row, "verdict": "MISSING", "action": "create"})
    return rows


def order(rows, planner_path: Path = PLANNER) -> list[dict]:
    """Lifecycle start order from the catalog planner; alphabetical fallback."""
    actions = [r for r in rows if r.get("action")]
    ids = sorted({r["app"] for r in actions})
    rank: dict[str, int] = {}
    if ids:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "apps.json"
            snapshot.write_text(json.dumps([{"id": i, "state": RUNNING} for i in ids]))
            result = subprocess.run(
                [sys.executable, str(planner_path), "--apps", str(snapshot)],
                capture_output=True, text=True, check=False,
            )
        if result.returncode == 0:
            rank = {app: i for i, app in enumerate(json.loads(result.stdout)["start_order"])}
    return sorted(actions, key=lambda r: (rank.get(r["app"], len(rank)), r["app"]))


def plan_hash(actions) -> str:
    stable = [{k: a.get(k) for k in ("app", "action", "compose", "orphans")} for a in actions]
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

    def apps(self) -> list[dict]:
        options = json.dumps({"select": ["id", "state", "custom_app"]})
        return json.loads(self._run(self.midclt, "call", "app.query", "[]", options))

    def containers(self) -> list[dict]:
        rows = []
        for line in self._run(self.docker, "ps", "-a", "--format", "{{json .}}").splitlines():
            raw = json.loads(line)
            labels = dict(kv.split("=", 1) for kv in raw.get("Labels", "").split(",") if "=" in kv)
            rows.append({"name": raw["Names"], "project": labels.get("com.docker.compose.project", "")})
        return rows

    def create(self, app_id: str, include: str) -> None:
        payload = {"app_name": app_id, "custom_app": True,
                   "custom_compose_config_string": f"include:\n  - {include}\n"}
        self._run(self.midclt, "call", "-j", "app.create", json.dumps(payload))

    def start(self, app_id: str) -> None:
        self._run(self.midclt, "call", "-j", "app.start", app_id)

    def remove_containers(self, names: list[str]) -> None:
        self._run(self.docker, "stop", *names)
        self._run(self.docker, "rm", *names)

    def wait_running(self, app_id: str, timeout: int) -> str:
        deadline = time.monotonic() + timeout
        state = "UNKNOWN"
        while time.monotonic() < deadline:
            state = next((a["state"] for a in self.apps() if a["id"] == app_id), "MISSING")
            if state in (RUNNING, "CRASHED", "MISSING"):
                return state
            time.sleep(5)
        return state


def apply(actions, args, runtime: Runtime) -> int:
    for row in actions:
        free = mem_available_gib(args.meminfo)
        if free < args.min_available_gib:
            print(f"STOP: {free:.1f} GiB available < floor {args.min_available_gib} GiB before {row['app']}")
            return 3
        include = f"{args.canonical_root}/{row['compose']}"
        if row["action"] == "adopt":
            if not args.adopt:
                print(f"SKIP: {row['app']} runs outside the UI; rerun with --adopt to replace it")
                continue
            runtime.remove_containers(row["orphans"])
            runtime.create(row["app"], include)
        elif row["action"] == "create":
            runtime.create(row["app"], include)
        else:
            runtime.start(row["app"])
        state = runtime.wait_running(row["app"], args.timeout)
        print(f"{'OK' if state == RUNNING else 'FAIL'}: {row['action']} {row['app']} -> {state}")
        if state != RUNNING:
            return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only (default)")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--apps-json", type=Path, help="app.query snapshot (offline check)")
    p.add_argument("--containers-json", type=Path, help="[{name, project}] snapshot")
    p.add_argument("--repo-root", type=Path, default=ROOT)
    p.add_argument("--canonical-root", default=CANONICAL_ROOT)
    p.add_argument("--expected-plan-hash")
    p.add_argument("--acknowledge", help=f"type {ACK} exactly")
    p.add_argument("--adopt", action="store_true", help="replace containers running outside the UI")
    p.add_argument("--min-available-gib", type=float, default=6.0)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--meminfo", type=Path, default=Path("/proc/meminfo"))
    p.add_argument("--midclt", default=os.environ.get("MIDCLT", "midclt"))
    p.add_argument("--docker", default=os.environ.get("DOCKER", "docker"))
    args = p.parse_args()

    runtime = Runtime(args.midclt, args.docker)
    apps = json.loads(args.apps_json.read_text()) if args.apps_json else runtime.apps()
    containers = (json.loads(args.containers_json.read_text())
                  if args.containers_json else runtime.containers())
    rows = classify(discover(args.repo_root), apps, containers, _planner())
    actions = order(rows)
    digest = plan_hash(actions)
    for row in sorted(rows, key=lambda r: (r.get("action") is None, r["dir"])):
        print(f"{row['verdict']:<30} {row.get('app') or '-':<24} {row.get('action') or '-':<7} {row['compose']}")
    print(f"plan_hash={digest} actions={len(actions)}")
    if not args.apply:
        return 0
    if args.acknowledge != ACK or args.expected_plan_hash != digest:
        print(f"REFUSED: --apply needs --expected-plan-hash {digest} and --acknowledge {ACK}")
        return 2
    return apply(actions, args, runtime)


if __name__ == "__main__":
    raise SystemExit(main())
