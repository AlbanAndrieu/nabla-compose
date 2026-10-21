#!/usr/bin/env python3
"""Safe, explicit, sequential TrueNAS App restart from the Backstage v2 crosswalk.

Default --check is read-only. Never bulk-stop workloads or infer health from Git.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys
import time
from collections.abc import Iterator

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
        if row.get("id") and row.get("name") and row["id"] != row["name"]:
            raise ValueError("TrueNAS App id/name mismatch: reconcile before restart")
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
            if len(providers) > 1:
                raise ValueError(f"ambiguous Backstage dependency provider: {ref}")
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
    deferred: set[str], runtime_root: Path | None,
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
        if row["vaultwardenManifest"] and row["runtimeSecretFile"] == "missing"
    )
    deferred_secrets = sorted(
        row["app"] for row in canonical_plan["waveOther"]
        if row["app"] in deferred and row["vaultwardenManifest"]
        and row["runtimeSecretFile"] == "missing"
    )
    unverified_running_secrets = sorted(
        row["app"] for row in active
        if row["vaultwardenManifest"] and row["runtimeSecretFile"] == "not-checked"
    )
    unverified_deferred_secrets = sorted(
        row["app"] for row in canonical_plan["waveOther"]
        if row["app"] in deferred and row["vaultwardenManifest"]
        and row["runtimeSecretFile"] == "not-checked"
    )
    entries = {row["app"]: row for phase in ("waveRunning", "waveOther", "blocked")
               for row in canonical_plan[phase]}
    gatus_entry = entries.get("gatus")
    declared_core_inactive = sorted(
        row["app"] for row in active
        if {"planned", "disabled"} & set(row["declaredStates"])
    )
    gatus_declared_inactive = bool(
        gatus_entry and {"planned", "disabled"} & set(gatus_entry["declaredStates"])
    )
    blocked_core = sorted(row["app"] for row in canonical_plan["blocked"]
                          if row["app"] != "gatus" and row["app"] not in deferred)
    blocked_deferred = sorted(row["app"] for row in canonical_plan["blocked"]
                              if row["app"] in deferred)
    declared_deferred = sorted(app for app in delayed
                               if {"planned", "disabled"} & set(
                                   entries.get(app, {}).get("declaredStates", [])))
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
        "gatusBlocked": bool(gatus_entry and gatus_entry.get("blockers")),
        "gatusDeclaredInactive": gatus_declared_inactive,
        "declaredCoreInactive": declared_core_inactive,
        "gatusMissingSecret": bool(gatus_entry and gatus_entry["vaultwardenManifest"]
                                   and gatus_entry["runtimeSecretFile"] == "missing"),
        "gatusSecretUnverified": bool(gatus_entry and gatus_entry["vaultwardenManifest"]
                                      and gatus_entry["runtimeSecretFile"] == "not-checked"),
        "blockedDeferredApps": blocked_deferred,
        "plannedOrDisabledDeferred": declared_deferred,
        "deferredLast": delayed,
        "runningDeferredExcluded": accidentally_running_deferred,
        "missingRunningSecrets": secret_blockers,
        "unverifiedRunningSecrets": unverified_running_secrets,
        "missingDeferredSecrets": deferred_secrets,
        "unverifiedDeferredSecrets": unverified_deferred_secrets,
        "unmappedApps": unmapped,
        "blockedApps": canonical_plan["blocked"],
        "blockedCoreApps": blocked_core,
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


def validate_wave(report: dict, wave: str) -> None:
    """Fail closed for the selected wave, without restarting unrelated workloads."""
    if wave == "core":
        if (report["blockedCoreApps"] or report["missingRunningSecrets"]
                or report["unverifiedRunningSecrets"] or report["declaredCoreInactive"]):
            raise RuntimeError("core blocked: unresolved mapping or runtime secrets")
        if report["runningDeferredExcluded"]:
            raise RuntimeError("running deferred Apps require manual classification")
    elif wave == "gatus":
        if report["states"].get("gatus") not in ("RUNNING", "STOPPED"):
            raise RuntimeError("Gatus must be present and RUNNING or STOPPED")
        if (report["gatusBlocked"] or report["gatusMissingSecret"]
                or report["gatusSecretUnverified"] or report["gatusDeclaredInactive"]):
            raise RuntimeError("Gatus blocked: unresolved mapping or runtime secrets")
    elif wave == "deferred":
        if (report["missingDeferredSecrets"] or report["unverifiedDeferredSecrets"]
                or report["blockedDeferredApps"] or report["plannedOrDisabledDeferred"]
                or report["runningDeferredExcluded"]):
            raise RuntimeError("deferred wave blocked: reconcile states, mappings and secrets")
    else:
        raise ValueError("unknown wave")


@contextlib.contextmanager
def mutation_lock() -> Iterator[None]:
    """Serialize mutating runs before reading live state or checking planHash.

    The file is a persistent coordination point; the kernel releases flock
    when the process exits, including after interruption or exception.
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if AUDIT_DIR.is_symlink():
        raise RuntimeError("audit directory must not be a symlink")
    os.chmod(AUDIT_DIR, 0o700)
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(AUDIT_DIR / ".catalog-v2-restart.lock", flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError("restart lock must be a regular file")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another TrueNAS Catalog v2 restart is running") from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


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


def wait_state(app: str, expected: str, timeout_seconds: int = 600) -> None:
    """Wait for middleware convergence; never start an app still stopping."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        current = state_by_app(query_apps()).get(app, "ABSENT")
        if current == expected:
            return
        if current in ("CRASHED", "ERROR", "ABSENT"):
            raise RuntimeError(f"{app}: unexpectedly reached {current}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{app}: timeout waiting for {expected}, observed {current}")
        time.sleep(5)


def verify(app: str) -> None:
    subprocess.run(
        ["bash", str(HEALTH_GATE), app],
        check=True, capture_output=True, timeout=930,
    )


def restart_one(app: str) -> None:
    assert_state(app, "RUNNING")
    print(f"STOP {app}", flush=True)
    middleware_action("stop", app)
    wait_state(app, "STOPPED")
    print(f"START {app}", flush=True)
    middleware_action("start", app)
    wait_state(app, "RUNNING")
    print(f"VERIFY {app}", flush=True)
    verify(app)
    print(f"OK {app}", flush=True)


def start_one(app: str) -> None:
    assert_state(app, "STOPPED")
    print(f"START {app}", flush=True)
    middleware_action("start", app)
    wait_state(app, "RUNNING")
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
    waves = parser.add_mutually_exclusive_group()
    waves.add_argument("--include-gatus", action="store_true",
                       help="select ONLY Gatus (does not restart core)")
    waves.add_argument("--include-deferred", action="store_true",
                       help="select ONLY STOPPED optional Apps (does not restart core)")
    args = parser.parse_args()
    if args.apply and (os.geteuid() != 0 or args.apps_json is not None):
        parser.error("--apply needs root and fresh live app.query")
    if args.apply and (
        args.acknowledge_downtime != ACK
        or not args.expected_plan_hash
        or not re.fullmatch("[a-f0-9]{64}", args.expected_plan_hash)
    ):
        parser.error("--apply requires exact acknowledgement and --expected-plan-hash")
    wave = "gatus" if args.include_gatus else "deferred" if args.include_deferred else "core"
    if args.apply:
        with mutation_lock():
            return execute_selected_wave(args, wave)
    return execute_selected_wave(args, wave)


def execute_selected_wave(args: argparse.Namespace, wave: str) -> int:
    """Check/apply one wave using a fresh snapshot under the mutation lock."""
    apps = read_json(args.apps_json) if args.apps_json else query_apps()
    report = make_plan(
        apps, read_json(CATALOG_FILE), read_json(IDENTITY_FILE),
        read_json(SECRETS_FILE), load_deferred(),
        None if args.apps_json else Path("/"),
    )
    # A confirmation obtained for Gatus must never authorize a core restart.
    report["planHash"] = hashlib.sha256(
        f"{report['planHash']}:{wave}".encode("utf-8")
    ).hexdigest()
    report["selectedWave"] = wave
    report["inventorySource"] = "snapshot" if args.apps_json else "live-midclt"
    report["runtimeSecretsSource"] = (
        "not-checked" if args.apps_json else "live-filesystem"
    )
    try:
        validate_wave(report, wave)
        selected_wave_ready = True
        selected_wave_blocker = None
    except RuntimeError as exc:
        selected_wave_ready = False
        selected_wave_blocker = str(exc)

    report["selectedWaveReady"] = selected_wave_ready
    report["selectedWaveBlocker"] = selected_wave_blocker
    if args.output:
        # Safe replace: do not truncate a pre-existing output or follow a link.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
        fd = os.open(args.output, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "selectedWaveReady": selected_wave_ready,
        "selectedWaveBlocker": selected_wave_blocker,
        "catalogRevision": report["catalogRevision"],
        "planHash": report["planHash"],
        "selectedWave": wave,
        "inventorySource": report["inventorySource"],
        "runtimeSecretsSource": report["runtimeSecretsSource"],
        "counts": report["counts"],
        "missingRunningSecrets": report["missingRunningSecrets"],
        "unverifiedRunningSecrets": report["unverifiedRunningSecrets"],
        "unverifiedDeferredSecrets": report["unverifiedDeferredSecrets"],
        "nonBlockingGatus": report["nonBlockingGatus"],
        "gatusBlocked": report["gatusBlocked"],
        "gatusDeclaredInactive": report["gatusDeclaredInactive"],
        "declaredCoreInactive": report["declaredCoreInactive"],
        "gatusMissingSecret": report["gatusMissingSecret"],
        "gatusSecretUnverified": report["gatusSecretUnverified"],
        "blockedCoreApps": report["blockedCoreApps"],
        "blockedDeferredApps": report["blockedDeferredApps"],
        "plannedOrDisabledDeferred": report["plannedOrDisabledDeferred"],
        "runningDeferredExcluded": report["runningDeferredExcluded"],
        "deferredLast": report["deferredLast"],
    }, indent=2), flush=True)

    if not args.apply:
        return 0
    if report["planHash"] != args.expected_plan_hash:
        raise RuntimeError("plan changed since --check; re-run --check")
    if not selected_wave_ready:
        raise RuntimeError(selected_wave_blocker or "selected wave preflight blocked")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(AUDIT_DIR, 0o700)
    journal = AUDIT_DIR / f"catalog-v2-{wave}-{time.time_ns()}-{report['planHash'][:12]}.jsonl"
    # Create 0600 from the first instant, not after a brief default-umask window.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    journal_fd = os.open(journal, flags, 0o600)
    with os.fdopen(journal_fd, "w", encoding="utf-8") as audit:
        os.fchmod(audit.fileno(), 0o600)
        failures: list[str] = []

        def execute(action: str, app: str, nonblocking: bool = False) -> None:
            entry = {"app": app, "action": action, "success": False}
            try:
                if action == "restart":
                    restart_one(app)
                else:
                    start_one(app)
                entry["success"] = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
                failures.append(app)
                entry["errorType"] = type(exc).__name__
                print(f"FAIL {app}: {type(exc).__name__}; review TrueNAS and {journal}", file=sys.stderr)
                if not nonblocking:
                    raise
            finally:
                audit.write(json.dumps(entry) + "\n")
                audit.flush()

        try:
            if wave == "core":
                for app in report["coreRestartOrder"]:
                    execute("restart", app)
            elif wave == "gatus":
                execute("start" if report["states"]["gatus"] == "STOPPED" else "restart",
                        "gatus", nonblocking=True)
            else:
                for app in report["deferredLast"]:
                    if report["states"][app] == "STOPPED":
                        execute("start", app, nonblocking=True)
                    else:
                        print(f"SKIP deferred {app}: state={report['states'][app]}")
        finally:
            print(f"Audit metadata only: {journal}", flush=True)
        if failures:
            print(f"FAIL: {len(failures)} App action(s) failed in {wave} wave",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {type(exc).__name__}: {str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'operation failed'}",
              file=sys.stderr)
        raise SystemExit(1) from None
