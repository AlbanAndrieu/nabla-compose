#!/usr/bin/env python3
"""Fast Talos 1.14.4 + Kubernetes 1.37.1 maintenance (one operator transaction).

All THREE Talos upgrades may start concurrently. With singleton etcd this
deliberately creates full-cluster downtime and may cause unrecoverable data
loss if an upgrade fails. Does not take an etcd snapshot by user request.
No --force, reset, bootstrap or skip of Talos's own etcd safety checks.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TARGET_TALOS = (ROOT / "config/talos/VERSION").read_text().strip()
TARGET_K8S = (ROOT / "config/talos/KUBERNETES_VERSION").read_text().strip()
NODES = ("172.17.0.50", "172.17.0.51", "172.17.0.52")
ACK = "I_ACCEPT_FULL_CLUSTER_OUTAGE_WITHOUT_ETCD_BACKUP"
# Single reviewed pin; the installer and server checks derive from it.
REVIEWED_TALOS, REVIEWED_K8S = "v1.14.4", "v1.37.1"
IMAGE = re.compile(
    rf"^factory\.talos\.dev/metal-installer/[a-f0-9]{{64}}:{re.escape(REVIEWED_TALOS)}$"
)
REQUIRED_SERVER_VERSION = re.compile(rf"(?m)^\s*Tag:\s*{re.escape(REVIEWED_TALOS)}\s*$")


def plan(image: str) -> dict:
    if TARGET_TALOS != REVIEWED_TALOS or TARGET_K8S != REVIEWED_K8S:
        raise ValueError("unreviewed Talos/Kubernetes version targets")
    if not IMAGE.fullmatch(image):
        raise ValueError("installer must be version-matched Image Factory schematic")
    base = {
        "talosTarget": TARGET_TALOS,
        "kubernetesTarget": TARGET_K8S,
        "nodes": list(NODES),
        "parallelTalos": 3,
        "installerImage": image,
        "downtime": "full-cluster",
        "etcdBackup": "not-required-at-operator-request",
        "scope": "upgrade-existing-nodes-only",
    }
    base["planHash"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return base


def run(command: list[str], timeout: int = 120) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True,
                            timeout=timeout)
    return result.stdout


def upgrade_node(ip: str, image: str) -> None:
    if ip not in NODES:
        raise ValueError("unexpected Talos target node")
    # Do not override Talos etcd quorum/health safety checks with --force.
    run(["talosctl", "--nodes", ip, "upgrade", "--image", image], timeout=1200)


def wait_node(ip: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            output = run(["talosctl", "--nodes", ip, "version"], timeout=20)
            # A new CLIENT version does not prove remote node recovery.
            server = output.partition("Server:")[2]
            if server and REQUIRED_SERVER_VERSION.search(server):
                return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            pass
        time.sleep(5)
    raise RuntimeError(f"Talos did not recover at target version: {ip}")


def failed_nodes(action, *args) -> list[str]:
    """Run action(ip, *args) on every node concurrently; return failed IPs."""
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=len(NODES)) as pool:
        jobs = {pool.submit(action, ip, *args): ip for ip in NODES}
        for future in as_completed(jobs):
            try:
                future.result()
            except Exception:
                failures.append(jobs[future])
    return sorted(failures)


def parallel_nodes(image: str, timeout: int) -> None:
    # Submit ALL THREE Talos upgrades, including singleton control-plane,
    # without serial worker waits. Do not submit Kubernetes until every
    # Talos node is at the target and the cluster preflight is green.
    failures = failed_nodes(upgrade_node, image)
    if failures:
        raise RuntimeError("Talos upgrades failed: " + ",".join(failures))
    failures = failed_nodes(wait_node, timeout)
    if failures:
        raise RuntimeError("Talos nodes did not recover: " + ",".join(failures))


def preflight() -> None:
    run(["python3", str(ROOT / "scripts/talos/preflight-supported-upgrade.py"),
         "--check"], timeout=120)


def canonical_checkout() -> None:
    branch = run(["git", "-C", str(ROOT), "symbolic-ref", "-q",
                  "--short", "HEAD"]).strip()
    dirty = run(["git", "-C", str(ROOT), "status", "--porcelain=v1"]).strip()
    if branch != "master" or dirty:
        raise RuntimeError("upgrade requires a clean reviewed master checkout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="read-only plan")
    actions.add_argument("--apply", action="store_true", help="cluster mutation")
    parser.add_argument("--installer-image", required=True,
                        help="verified output of scripts/talos/image-factory.sh")
    parser.add_argument("--expected-plan-hash", default="")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--recovery-timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if not 120 <= args.recovery_timeout <= 3600:
        parser.error("--recovery-timeout outside approved 120..3600 seconds")
    try:
        report = plan(args.installer_image)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.apply:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.acknowledge != ACK or args.expected_plan_hash != report["planHash"]:
        parser.error("full-cluster/no-etcd-backup acknowledgement and plan hash required")
    try:
        canonical_checkout()
        preflight()
        # The currently running Talos release might not support the NEW
        # Kubernetes minor. Dry-run only once target Talos is online.
        parallel_nodes(args.installer_image, args.recovery_timeout)
        preflight()
        run(["talosctl", "--nodes", NODES[0], "upgrade-k8s",
             "--to", TARGET_K8S.removeprefix("v"), "--dry-run"], timeout=120)
        run(["talosctl", "--nodes", NODES[0], "upgrade-k8s",
             "--to", TARGET_K8S.removeprefix("v")], timeout=1800)
        preflight()
        print("OK: Talos and Kubernetes upgraded; validate CSI and services separately")
        return 0
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"BLOCKED: mass cluster upgrade interrupted ({type(exc).__name__})",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
