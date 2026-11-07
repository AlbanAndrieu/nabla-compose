#!/usr/bin/env python3
"""Redeploy only the TrueNAS Apps whose repository files changed, providers first.

Run from the deployment checkout. Plan (default, read-only): map the files
changed between --from and --to to catalog Apps, keep the RUNNING Custom Apps
whose config includes this checkout's Compose file, order them so catalog
dependsOn providers come first, and list the RUNNING dependents to check after.

Apply (root, NABLA_IMPACTED_REDEPLOY_APPROVED=yes, clean checkout at --to):
app.redeploy each App in order and wait until it is RUNNING with healthy
containers, then restart a dependent only if it turned unhealthy. Stops at the
first App that does not converge. STOPPED Apps are never started.
"""
from __future__ import annotations

import argparse
import graphlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from nabla_ops.catalog import declared_apps, load_catalog  # noqa: E402

ACK = "NABLA_IMPACTED_REDEPLOY_APPROVED"
# Lifecycles with steps beyond app.redeploy that are not named deploy-<app>.sh.
DEDICATED = {"sample": "update-fastapi-sample.sh"}


def changed_app_dirs(paths: list[str]) -> set[str]:
    """apps/<dir> touched by a change; Markdown is never read by a container."""
    return {path.split("/")[1] for path in paths if path.startswith("apps/") and not path.endswith(".md")}


def app_dependencies(topology: dict, rows: list[dict]) -> dict[str, set[str]]:
    """App id -> App ids it depends on, from service-level catalog dependsOn."""
    app_of = {sid: row["runtimeId"] for row in rows if row["runtimeId"] for sid in row["serviceIds"]}
    deps: dict[str, set[str]] = {app: set() for app in app_of.values()}
    for relation in topology.get("relations", []):
        if relation.get("type") != "dependsOn":
            continue
        source, target = app_of.get(relation["source"]), app_of.get(relation["target"])
        if source and target and source != target:
            deps[source].add(target)
    return deps


def dedicated_script(directory: str, app: str) -> str | None:
    for name in (DEDICATED.get(app), f"deploy-{directory}.sh", f"deploy-{app}.sh"):
        if name and (ROOT / "scripts/truenas" / name).is_file():
            return f"scripts/truenas/{name}"
    return None


def build_plan(
    changed: set[str],
    rows: list[dict],
    deps: dict[str, set[str]],
    states: dict[str, str],
    includes_checkout: Callable[[str, str], bool],
) -> dict:
    by_dir = {row["app"]: row for row in rows}
    selected: list[str] = []
    dedicated: list[str] = []
    skipped: list[str] = []
    for directory in sorted(changed):
        row = by_dir.get(directory)
        if row is None:
            skipped.append(f"{directory} (not in the service catalog)")
            continue
        app = row["runtimeId"] or directory
        script = dedicated_script(directory, app)
        if not row["initializationEligible"]:
            reason = row["mappingError"] or row["statusError"] or (
                "manual-only" if row["manual"] else f"catalog status {row['status']}"
            )
        elif script:
            dedicated.append(f"{app} ({script})")
            continue
        elif app not in states:
            reason = "no TrueNAS App with this id"
        elif states[app] != "RUNNING":
            reason = f"{states[app]}, left as is"
        elif not includes_checkout(app, row["sourcePath"]):
            reason = "its Custom App config does not include this checkout's Compose file"
        else:
            selected.append(app)
            continue
        skipped.append(f"{app} ({reason})")

    blocked = None
    try:
        order = list(graphlib.TopologicalSorter(
            {app: deps.get(app, set()) & set(selected) for app in selected}
        ).static_order())
    except graphlib.CycleError as error:
        order, blocked = [], f"dependency cycle: {' -> '.join(error.args[1])}"
    watch = sorted(
        app for app, providers in deps.items()
        if providers & set(order) and app not in order and states.get(app) == "RUNNING"
    )
    return {"redeploy": order, "dedicated": dedicated, "skipped": skipped,
            "watch": watch, "blocked": blocked}


def render(plan: dict) -> str:
    lines = [f"redeploy in dependency order: {', '.join(plan['redeploy']) or 'none'}"]
    if plan["blocked"]:
        lines.append(f"BLOCKED: {plan['blocked']}")
    if plan["dedicated"]:
        lines.append(f"dedicated lifecycle, run by hand: {', '.join(plan['dedicated'])}")
    if plan["skipped"]:
        lines.append(f"skipped: {', '.join(plan['skipped'])}")
    if plan["watch"]:
        lines.append(
            f"dependents checked afterwards, restarted only if unhealthy: {', '.join(plan['watch'])}"
        )
    return "\n".join(f"  {line}" for line in lines)


def midclt(args: list[str], timeout: int = 120) -> str:
    base = ["midclt", "call", *args]
    attempts = [base] if os.geteuid() == 0 else [base, ["sudo", "-n", *base]]
    for command in attempts:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
        if result.returncode == 0:
            return result.stdout
    raise RuntimeError(f"midclt call {args[0]} failed: {result.stderr.strip()[-300:]}")


def app_states(app_filter: str = "[]") -> dict[str, str]:
    rows = json.loads(midclt(["app.query", app_filter, '{"select":["id","state"]}'], timeout=60))
    return {row["id"]: row["state"] for row in rows}


def container_problem(status: str) -> str | None:
    """None when a `docker ps` status is healthy; one-shot jobs may exit 0."""
    if status.startswith("Up"):
        if "(unhealthy)" in status:
            return "unhealthy"
        return "health: starting" if "(health: starting)" in status else None
    if status.startswith("Exited (0)"):
        return None
    return status.split(" ", 1)[0].lower()


def app_health(app: str) -> str | None:
    try:
        state = app_states(json.dumps([["id", "=", app]])).get(app, "MISSING")
        if state != "RUNNING":
            return state
        listing = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project=ix-{app}",
             "--format", "{{.Names}}\t{{.Status}}"],
            text=True, capture_output=True, timeout=60, check=True,
        ).stdout
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        return f"health unknown ({error})"
    for line in listing.splitlines():
        name, _, status = line.partition("\t")
        problem = container_problem(status)
        if problem:
            return f"{name} {problem}"
    return None


def wait_healthy(app: str, health: Callable[[str], str | None], sleep: Callable[[float], None],
                 timeout: int, poll: int = 10) -> str | None:
    problem = None
    for _ in range(max(1, timeout // poll)):
        problem = health(app)
        if problem is None or problem in ("CRASHED", "MISSING"):
            return problem
        sleep(poll)
    return problem


def apply(plan: dict, deps: dict[str, set[str]], states: dict[str, str],
          redeploy: Callable[[str], None], health: Callable[[str], str | None],
          sleep: Callable[[float], None] = time.sleep, grace: int = 60, timeout: int = 600) -> int:
    def converge(app: str) -> str | None:
        try:
            redeploy(app)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            return f"app.redeploy failed: {error}"
        return wait_healthy(app, health, sleep, timeout)

    order = plan["redeploy"]
    for index, app in enumerate(order):
        problem = converge(app)
        if problem:
            print(f"FAIL: {app} not healthy after app.redeploy ({problem}); "
                  f"stopped before: {', '.join(order[index + 1:]) or 'nothing'}")
            return 1
        print(f"OK: {app} redeployed and healthy")

    queue, seen = list(plan["watch"]), set(order)
    if queue:
        sleep(grace)
    while queue:
        app = queue.pop(0)
        if app in seen:
            continue
        seen.add(app)
        problem = health(app)
        if problem is None:
            print(f"OK: dependent {app} healthy, not restarted")
            continue
        print(f"RESTART: dependent {app} unhealthy ({problem})")
        problem = converge(app)
        if problem:
            print(f"FAIL: dependent {app} still unhealthy ({problem})")
            return 1
        print(f"OK: dependent {app} restarted and healthy")
        queue += sorted(a for a, providers in deps.items()
                        if app in providers and states.get(a) == "RUNNING")
    return 0


def git(*args: str) -> str:
    return subprocess.run(["git", *args], text=True, capture_output=True, check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="base", required=True, help="revision deployed before the change")
    parser.add_argument("--to", dest="head", default="HEAD")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--timeout", type=int, default=600, help="seconds for each App to converge")
    args = parser.parse_args()

    base, head = git("rev-parse", args.base), git("rev-parse", args.head)
    changed = changed_app_dirs(git("diff", "--no-renames", "--name-only", base, head).splitlines())
    print(f"Impacted TrueNAS Apps for {base[:12]}..{head[:12]}:")
    if not changed:
        print("  no apps/ change outside Markdown; nothing to redeploy")
        return 0
    rows = declared_apps(load_catalog(ROOT / "catalog/services.json"), root=ROOT)
    deps = app_dependencies(load_catalog(ROOT / "catalog/service-topology.json"), rows)
    checkout = Path.cwd()
    try:
        states = app_states()
        # shortcut: substring match on the app.config JSON; enough for include-bound Custom Apps.
        plan = build_plan(changed, rows, deps, states,
                          lambda app, source: str(checkout / source) in midclt(["app.config", app]))
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"  TrueNAS state unavailable ({error}); changed apps/ dirs: {', '.join(sorted(changed))}")
        return 1
    print(render(plan))
    if not args.apply:
        if plan["redeploy"]:
            print(f"  apply: sudo {ACK}=yes python3 scripts/truenas/redeploy-impacted-apps.py "
                  f"--from {base[:12]} --to {head[:12]} --apply")
        return 0

    if os.geteuid() != 0 or os.environ.get(ACK) != "yes":
        print(f"ERROR: --apply requires root and {ACK}=yes", file=sys.stderr)
        return 2
    if head != git("rev-parse", "HEAD") or git("status", "--porcelain", "--untracked-files=no",
                                               "--ignore-submodules=all"):
        print("ERROR: --apply requires a clean checkout at --to: Apps include the files on disk",
              file=sys.stderr)
        return 2
    if plan["blocked"]:
        return 1

    def redeploy(app: str) -> None:
        print(f"app.redeploy {app}")
        midclt(["-j", "app.redeploy", app], timeout=1800)

    return apply(plan, deps, states, redeploy, app_health, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
