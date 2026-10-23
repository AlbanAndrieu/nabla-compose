#!/usr/bin/env python3
"""Parallel TrueNAS App image pull/redeploy with an explicit immutable plan.

app.redeploy stops, pulls and restarts an installed App (TrueNAS v26).
It DOES NOT change a pinned Compose tag or upgrade an installed chart.
Only apps already RUNNING are selected; STOPPED apps stay STOPPED.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
CRITICAL = {
    "docker-socket-proxy", "vaultwarden", "pihole", "adguard-home",
    "traefik", "cloudflared", "postgres", "mongo", "redis", "kafka",
    "clickhouse", "opensearch", "sentry-clickhouse", "garage",
    "prometheus", "grafana",
}
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ACK = "I_ACCEPT_BULK_TRUENAS_APP_DOWNTIME"


def shell(command: list[str], timeout: int = 1800) -> str:
    return subprocess.run(command, text=True, capture_output=True,
                          check=True, timeout=timeout).stdout


def query() -> list[dict]:
    result = json.loads(shell(["midclt", "call", "app.query"], timeout=90))
    if not isinstance(result, list):
        raise ValueError("TrueNAS app.query must be an array")
    return result


def make_plan(apps: list[dict], scope: str, workers: int) -> dict:
    if scope not in ("applications", "all") or not 1 <= workers <= 16:
        raise ValueError("invalid app scope or concurrency")
    selected: set[str] = set()
    excluded: set[str] = set()
    revisions: dict[str, str] = {}
    chart_pending: list[str] = []
    image_pending: list[str] = []
    for app in apps:
        if not isinstance(app, dict):
            raise ValueError("malformed TrueNAS App record")
        name = app.get("id") or app.get("name")
        if (not isinstance(name, str) or not ID.fullmatch(name)
                or (app.get("id") and app.get("name") and app["id"] != app["name"])):
            raise ValueError("unsafe TrueNAS App name or identity drift")
        if name in revisions:
            raise ValueError("duplicate TrueNAS App ID")
        # Include version/image-change state in the plan fingerprint. The
        # operator must re-review if a registry pull/chart upgrade was
        # discovered between preview and apply.
        identity = {key: app.get(key) for key in (
            "state", "images", "version", "latest_version",
            "upgrade_available", "image_updates_available", "custom_app",
        )}
        revisions[name] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, default=str).encode()
        ).hexdigest()
        if app.get("upgrade_available") is True:
            chart_pending.append(name)
        if app.get("image_updates_available") is True:
            image_pending.append(name)
        if app.get("state") == "RUNNING":
            if scope == "applications" and name in CRITICAL:
                excluded.add(name)
            else:
                selected.add(name)
        else:
            excluded.add(name)
    waves = []
    if scope == "all":
        waves.append({"name": "foundation", "apps": sorted(selected & CRITICAL)})
    waves.append({"name": "applications", "apps": sorted(selected - CRITICAL)})
    report = {
        "scope": scope, "parallelism": workers, "waves": waves,
        "excluded": sorted(excluded), "selectedCount": len(selected),
        "inventoryRevisionHashes": {k: revisions[k] for k in sorted(revisions)},
        "chartUpgradesPending": sorted(chart_pending),
        "imageUpdatesAvailable": sorted(image_pending),
        "operation": "app.redeploy", "requiresState": "RUNNING",
        "mayPullNewImages": True, "upgradesChartOrPinnedTag": False,
    }
    report["planHash"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report



# TrueNAS middleware RUNNING does not mean every required Docker process
# is healthy. Reject bulk mutation if an App selected by the operator is
# already broken; recovery belongs to a separate, scoped runbook.
RUNTIME_PREREQUISITES = {
    "prometheus": ("prometheus",),
    "openrag": ("openrag-backend", "openrag-frontend"),
    "gatus": ("gatus",),
}


def selected_runtime_blockers(report: dict) -> list[str]:
    """Read-only fixed-identity Docker gate before bulk redeployment."""
    selected = {app for wave in report["waves"] for app in wave["apps"]}
    blocked: list[str] = []
    for app in sorted(selected & RUNTIME_PREREQUISITES.keys()):
        for container in RUNTIME_PREREQUISITES[app]:
            try:
                state = shell(
                    ["docker", "inspect", "--type", "container", "--format",
                     "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                     container],
                    timeout=10
                ).strip()
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                blocked.append(app)
                break
            parts = state.split("|")
            if len(parts) != 2 or parts[0] != "running" or parts[1] in (
                    "unhealthy", "starting", "unknown"):
                blocked.append(app)
                break
    return blocked


def redeploy(app: str) -> None:
    if not ID.fullmatch(app):
        raise ValueError("invalid App")
    shell(["midclt", "call", "-j", "app.redeploy", app])


def verify(app: str) -> None:
    shell(["bash", str(ROOT / "scripts/truenas/verify-app-runtime-health.sh"), app],
          timeout=1000)


def refresh(app: str, stop: threading.Event) -> str | None:
    """Redeploy then health-gate one App; return the failed stage, if any."""
    if stop.is_set():
        return "skipped"
    for stage, step in (("redeploy", redeploy), ("health", verify)):
        try:
            step(app)
        except Exception:
            stop.set()
            return stage
    return None


def execute(report: dict) -> int:
    for wave in report["waves"]:
        names = wave["apps"]
        if not names:
            continue
        print(f"START {wave['name']} count={len(names)} parallel={report['parallelism']}",
              flush=True)
        # Each App is verified as soon as its own redeploy ends, not after the
        # slowest pull of the wave. The first failure stops Apps not yet
        # started; the next wave is never submitted after a failure.
        failures: list[str] = []
        skipped: list[str] = []
        stop = threading.Event()
        with ThreadPoolExecutor(max_workers=report["parallelism"]) as pool:
            jobs = {pool.submit(refresh, name, stop): name for name in names}
            for job in as_completed(jobs):
                stage = job.result()
                if stage == "skipped":
                    skipped.append(jobs[job])
                elif stage is not None:
                    failures.append(f"{jobs[job]}:{stage}")
        if failures:
            print("BLOCKED " + ",".join(sorted(failures))
                  + (" skipped=" + ",".join(sorted(skipped)) if skipped else ""),
                  file=sys.stderr)
            return 1
        print(f"OK {wave['name']} verified={len(names)}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--scope", choices=["applications", "all"],
                        default="applications")
    parser.add_argument("--parallel", type=int, default=6)
    parser.add_argument("--expected-plan-hash", default="")
    parser.add_argument("--acknowledge", default="")
    args = parser.parse_args(argv)
    if not 1 <= args.parallel <= 16:
        parser.error("--parallel must be between 1 and 16")
    if args.apply:
        if args.acknowledge != ACK or not re.fullmatch(
                r"[a-f0-9]{64}", args.expected_plan_hash):
            parser.error("exact downtime acknowledgement and plan hash required")
        if os.geteuid() != 0:
            parser.error("TrueNAS apply requires root")
        try:
            branch = shell(["git", "-C", str(ROOT), "symbolic-ref",
                            "-q", "--short", "HEAD"]).strip()
            dirty = shell(["git", "-C", str(ROOT), "status",
                           "--porcelain=v1"]).strip()
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            parser.error("cannot confirm reviewed canonical checkout")
        if branch != "master" or dirty or str(ROOT) != "/mnt/cpool/compose/nabla-compose":
            parser.error("apply requires clean master on canonical TrueNAS checkout")
    try:
        report = make_plan(query(), args.scope, args.parallel)
        if not args.apply:
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        # report comes from a live app.query taken just now: comparing it with
        # the reviewed hash already detects drift, no second full query needed.
        if args.expected_plan_hash != report["planHash"]:
            raise RuntimeError("App states changed since plan; rerun --check")
        blockers = selected_runtime_blockers(report)
        if blockers:
            print("BLOCKED bulk redeploy: selected Apps not Docker-ready: "
                  + ",".join(blockers)
                  + "; repair each App before using a fleet-wide operation",
                  file=sys.stderr)
            return 1
        return execute(report)
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED bulk Apps operation ({type(exc).__name__})",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
