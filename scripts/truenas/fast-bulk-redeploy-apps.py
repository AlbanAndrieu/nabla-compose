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
    selected = set()
    excluded = []
    revisions: dict[str, str] = {}
    for app in apps:
        if not isinstance(app, dict):
            raise ValueError("malformed TrueNAS App record")
        name = app.get("id") or app.get("name")
        if (not isinstance(name, str) or not ID.fullmatch(name)
                or (app.get("id") and app.get("name") and app["id"] != app["name"])):
            raise ValueError("unsafe TrueNAS App name or identity drift")
        if name in selected or name in excluded or name in revisions:
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
        if app.get("state") == "RUNNING":
            if scope == "applications" and name in CRITICAL:
                excluded.append(name)
            else:
                selected.add(name)
        else:
            excluded.append(name)
    waves = []
    if scope == "all":
        waves.append({"name": "foundation", "apps": sorted(selected & CRITICAL)})
    waves.append({"name": "applications", "apps": sorted(selected - CRITICAL)})
    report = {
        "scope": scope, "parallelism": workers, "waves": waves,
        "excluded": sorted(excluded), "selectedCount": len(selected),
        "inventoryRevisionHashes": {k: revisions[k] for k in sorted(revisions)},
        "operation": "app.redeploy", "requiresState": "RUNNING",
        "mayPullNewImages": True, "upgradesChartOrPinnedTag": False,
    }
    report["planHash"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def redeploy(app: str) -> None:
    if not ID.fullmatch(app):
        raise ValueError("invalid App")
    shell(["midclt", "call", "-j", "app.redeploy", app])


def verify(app: str) -> None:
    shell(["bash", str(ROOT / "scripts/truenas/verify-app-runtime-health.sh"), app],
          timeout=1000)


def execute(report: dict) -> int:
    failures: list[str] = []
    for wave in report["waves"]:
        names = wave["apps"]
        if not names:
            continue
        print(f"START {wave['name']} count={len(names)} parallel={report['parallelism']}",
              flush=True)
        # Do not submit a second wave if any first-wave App failed.
        with ThreadPoolExecutor(max_workers=report["parallelism"]) as pool:
            jobs = {pool.submit(redeploy, name): name for name in names}
            for job in as_completed(jobs):
                try:
                    job.result()
                except Exception:
                    failures.append(jobs[job])
        if failures:
            print("BLOCKED redeploy: " + ",".join(sorted(failures)), file=sys.stderr)
            return 1
        with ThreadPoolExecutor(max_workers=report["parallelism"]) as pool:
            jobs = {pool.submit(verify, name): name for name in names}
            for job in as_completed(jobs):
                try:
                    job.result()
                except Exception:
                    failures.append(jobs[job])
        if failures:
            print("BLOCKED health: " + ",".join(sorted(failures)), file=sys.stderr)
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
        if args.expected_plan_hash != report["planHash"]:
            raise RuntimeError("App states changed since plan; rerun --check")
        # Always re-check live state of every targeted App immediately before apply.
        if make_plan(query(), args.scope, args.parallel)["planHash"] != report["planHash"]:
            raise RuntimeError("App inventory drift before mutation")
        return execute(report)
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED bulk Apps operation ({type(exc).__name__})",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
