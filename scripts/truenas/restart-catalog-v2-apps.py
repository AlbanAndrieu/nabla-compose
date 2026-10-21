#!/usr/bin/env python3
"""Safe, explicit, sequential TrueNAS App restart from the Backstage v2 crosswalk.

Default --check is read-only. Never bulk-stop workloads or infer health from Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DEFERRED_FILE = ROOT / "config/truenas/restore-optional-apps.txt"
CATALOG_FILE = ROOT / "catalog/generated/entities.json"
IDENTITY_FILE = ROOT / "catalog/generated/identity-map.json"
SECRETS_FILE = ROOT / "config/secrets/manifest.json"
PLANNER = ROOT / "scripts/truenas/plan-catalog-v2-restart.py"
HEALTH_GATE = ROOT / "scripts/truenas/verify-app-runtime-health.sh"
AUDIT_DIR = Path("/mnt/cpool/var/nabla/restart")
ACK = "I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART"
FOUNDATION = (
    "docker-socket-proxy", "vaultwarden", "pihole", "adguard-home",
    "traefik", "cloudflared", "postgres", "mongo", "redis", "kafka",
    "clickhouse", "opensearch", "sentry-clickhouse", "garage",
    "prometheus", "grafana",
)
APP_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_deferred(path: Path = DEFERRED_FILE) -> set[str]:
    apps = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        name = raw.split("#", 1)[0].strip()
        if not name:
            continue
        if not APP_NAME.fullmatch(name):
            raise ValueError("invalid deferred TrueNAS App ID")
        apps.add(name)
    if "gatus" in apps:
        raise ValueError("gatus must be its own non-blocking wave")
    if "vaultwarden" in apps or "docker-socket-proxy" in apps:
        raise ValueError("critical infrastructure cannot be deferred")
    return apps


def query_apps() -> list[dict]:
    result = subprocess.run(
        ["midclt", "call", "app.query"],
        check=True, text=True, capture_output=True, timeout=90,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, list):
        raise ValueError("TrueNAS app.query must return an array")
    return data


def state_by_app(apps: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in apps:
        name = row.get("id") or row.get("name")
        if not isinstance(name, str) or not APP_NAME.fullmatch(name):
            raise ValueError("TrueNAS app.query returned an invalid App ID")
        if name in result:
            raise ValueError("TrueNAS app.query returned duplicate App IDs")
        result[name] = str(row.get("state") or "UNKNOWN").upper()
    return result


def dependency_order(running: list[dict]) -> list[str]:
    """Topological order of verified v2 relations, with stable foundation tie-break."""
    selected = {row["app"] for row in running}
    ref_to_apps: dict[str, set[str]] = {}
    for row in running:
        for ref in row["entityRefs"]:
            ref_to_apps.setdefault(ref, set()).add(row["app"])
    edges: dict[str, set[str]] = {name: set() for name in selected}
    incoming: dict[str, set[str]] = {name: set() for name in selected}
    for row in running:
        name = row["app"]
        for ref in row["dependsOn"]:
            providers = ref_to_apps.get(ref, set())
            if len(providers) == 1:
                provider = next(iter(providers))
                if provider != name:
                    edges[provider].add(name)
                    incoming[name].add(provider)

    def priority(name: str) -> tuple[int, str]:
        return (FOUNDATION.index(name) if name in FOUNDATION else len(FOUNDATION), name)

    order: list[str] = []
    ready = {name for name in selected if not incoming[name]}
    while ready:
        name = min(ready, key=priority)
        ready.remove(name)
        order.append(name)
        for consumer in edges[name]:
            incoming[consumer].remove(name)
            if not incoming[consumer]:
                ready.add(consumer)
    if len(order) != len(selected):
        raise ValueError("cycle in Backstage dependencies: stop and review mapping")
    return order


def make_plan(
    apps: list[dict], catalog: dict, crosswalk: dict, manifest: dict,
    deferred: set[str], runtime_root: Path,
) -> dict:
    canonical_plan = runpy.run_path(str(PLANNER))["plan"](
        catalog, crosswalk, manifest, apps, runtime_root
    )
    states = state_by_app(apps)
    active = [row for row in canonical_plan["waveRunning"]
              if row["app"] not in deferred and row["app"] != "gatus"]
    accidentally_running_deferred = [
        row["app"] for row in canonical_plan["waveRunning"] if row["app"] in deferred
    ]
    core = dependency_order(active)
    gatus = sorted(set(states) & {"gatus"})
    delayed = sorted(set(states) & deferred)
    secret_blockers = sorted(
        row["app"] for row in active
        if row["vaultwardenManifest"] and row["runtimeSecretFile"] != "present"
    )
    deferred_secrets = sorted(
        row["app"] for row in canonical_plan["waveOther"]
        if row["app"] in deferred and row["vaultwardenManifest"]
        and row["runtimeSecretFile"] != "present"
    )
    unmapped = sorted({
        row["app"] for phase in ("waveRunning", "waveOther")
        for row in canonical_plan[phase] if not row["entityRefs"]
    })
    report = {
        "schemaVersion": 1,
        "catalogRevision": catalog["catalogRevision"],
        "mode": "read-only-check",
        "states": states,
        "coreRestartOrder": core,
        "nonBlockingGatus": gatus,
        "deferredLast": delayed,
        "runningDeferredExcluded": accidentally_running_deferred,
        "missingRunningSecrets": secret_blockers,
        "missingDeferredSecrets": deferred_secrets,
        "unmappedApps": unmapped,
        "blockedApps": canonical_plan["blocked"],
        "counts": {
            "running": sum(state == "RUNNING" for state in states.values()),
            "stopped": sum(state == "STOPPED" for state in states.values()),
            "coreRestart": len(core),
            "deferredLast": len(delayed),
            "unmapped": len(unmapped),
            "missingRunningSecrets": len(secret_blockers),
        },
    }
    fingerprint = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["planHash"] = hashlib.sha256(fingerprint.encode()).hexdigest()
    return report


def middleware_action(action: str, app: str, timeout: int = 900) -> None:
    if action not in ("start", "stop") or not APP_NAME.fullmatch(app):
        raise ValueError("unsafe App or action")
    subprocess.run(
        ["midclt", "call", "-j", f"app.{action}", app],
        check=True, capture_output=True, timeout=timeout,
    )


def assert_state(app: str, expected: str) -> None:
    current = state_by_app(query_apps()).get(app, "ABSENT")
    if current != expected:
        raise RuntimeError(
            f"{app}: expected TrueNAS state {expected}, observed {current}"
        )


def verify(app: str) -> None:
    subprocess.run(
        ["bash", str(HEALTH_GATE), app],
        check=True, capture_output=True, timeout=930,
    )


def restart_one(app: str) -> None:
    assert_state(app, "RUNNING")
    print(f"STOP {app}", flush=True)
    middleware_action("stop", app)
    assert_state(app, "STOPPED")
    print(f"START {app}", flush=True)
    middleware_action("start", app)
    assert_state(app, "RUNNING")
    print(f"VERIFY {app}", flush=True)
    verify(app)
    print(f"OK {app}", flush=True)


def start_one(app: str) -> None:
    assert_state(app, "STOPPED")
    print(f"START {app}", flush=True)
    middleware_action("start", app)
    assert_state(app, "RUNNING")
    verify(app)
    print(f"OK {app}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="default, read-only")
    mode.add_argument("--apply", action="store_true", help="mutates Apps")
    parser.add_argument("--apps-json", type=Path,
                        help="read-only offline snapshot, forbidden with --apply")
    parser.add_argument("--output", type=Path, help="private plan JSON (0600)")
    parser.add_argument("--expected-plan-hash", help="from the most recent --check")
    parser.add_argument("--acknowledge-downtime", help=f"type {ACK} exactly")
    parser.add_argument("--include-gatus", action="store_true",
                        help="attempt Gatus separately; never block other waves")
    parser.add_argument("--include-deferred", action="store_true",
                        help="start STOPPED non-essential apps after core")
    args = parser.parse_args()
    if args.apply and (os.geteuid() != 0 or args.apps_json is not None):
        parser.error("--apply needs root and fresh live app.query")
    if args.apply and (
        args.acknowledge_downtime != ACK
        or not args.expected_plan_hash
        or not re.fullmatch("[a-f0-9]{64}", args.expected_plan_hash)
    ):
        parser.error("--apply requires exact acknowledgement and --expected-plan-hash")
    if not args.apply and (args.include_gatus or args.include_deferred):
        parser.error("wave opt-ins only apply with --apply")

    apps = read_json(args.apps_json) if args.apps_json else query_apps()
    report = make_plan(
        apps, read_json(CATALOG_FILE), read_json(IDENTITY_FILE),
        read_json(SECRETS_FILE), load_deferred(), Path("/"),
    )
    if args.output:
        args.output.write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(args.output, 0o600)
    print(json.dumps({
        "catalogRevision": report["catalogRevision"],
        "planHash": report["planHash"],
        "counts": report["counts"],
        "missingRunningSecrets": report["missingRunningSecrets"],
        "nonBlockingGatus": report["nonBlockingGatus"],
        "runningDeferredExcluded": report["runningDeferredExcluded"],
        "deferredLast": report["deferredLast"],
    }, indent=2), flush=True)

    if not args.apply:
        return 0
    if report["planHash"] != args.expected_plan_hash:
        raise RuntimeError("plan changed since --check; re-run --check")
    if report["blockedApps"] or report["missingRunningSecrets"]:
        raise RuntimeError("core restart preflight blocked: unresolved dependencies or missing runtime secret files")
    if report["runningDeferredExcluded"]:
        raise RuntimeError("deferred App already RUNNING; inspect and classify before restart")
    if args.include_deferred and report["missingDeferredSecrets"]:
        raise RuntimeError("deferred-wave runtime secrets missing; do not start")
    if args.include_deferred:
        reference = {row["app"]: row for row in runpy.run_path(str(PLANNER))["plan"](
            read_json(CATALOG_FILE), read_json(IDENTITY_FILE),
            read_json(SECRETS_FILE), apps, Path("/"))["waveOther"]}
        if any("disabled" in reference.get(app, {}).get("declaredStates", [])
               or "planned" in reference.get(app, {}).get("declaredStates", [])
               for app in report["deferredLast"]):
            raise RuntimeError("deferred Apps include planned/disabled workloads")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(AUDIT_DIR, 0o700)
    journal = AUDIT_DIR / f"catalog-v2-{int(time.time())}-{report['planHash'][:12]}.jsonl"
    with journal.open("x", encoding="utf-8") as audit:
        os.chmod(journal, 0o600)

        def execute(action: str, app: str, nonblocking: bool = False) -> None:
            entry = {"app": app, "action": action, "success": False}
            try:
                if action == "restart":
                    restart_one(app)
                else:
                    start_one(app)
                entry["success"] = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
                entry["errorType"] = type(exc).__name__
                print(f"FAIL {app}: {type(exc).__name__}; review TrueNAS and {journal}", file=sys.stderr)
                if not nonblocking:
                    raise
            finally:
                audit.write(json.dumps(entry) + "\n")
                audit.flush()

        try:
            for app in report["coreRestartOrder"]:
                execute("restart", app)
            if args.include_gatus and "gatus" in report["nonBlockingGatus"]:
                execute("start" if report["states"]["gatus"] == "STOPPED" else "restart",
                        "gatus", nonblocking=True)
            if args.include_deferred:
                for app in report["deferredLast"]:
                    if report["states"][app] == "STOPPED":
                        execute("start", app, nonblocking=True)
                    else:
                        print(f"SKIP deferred {app}: state={report['states'][app]}")
        finally:
            print(f"Audit metadata only: {journal}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {type(exc).__name__}: {str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'operation failed'}",
              file=sys.stderr)
        raise SystemExit(1) from None
