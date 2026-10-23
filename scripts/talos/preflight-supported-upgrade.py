#!/usr/bin/env python3
"""Read-only Talos/Kubernetes upgrade acceptance gate.

Uses the live Kubernetes API, *never* changes cluster state. For tests,
--nodes-json takes a synthetic kubectl payload and bypasses network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ("172.17.0.50", "172.17.0.51", "172.17.0.52")


def validate_nodes(payload: object, expected: int = 3) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ["invalid kubectl nodes response"]
    nodes = payload["items"]
    problems = []
    if len(nodes) != expected:
        problems.append(f"expected {expected} nodes, got {len(nodes)}")
    for node in nodes:
        if not isinstance(node, dict):
            problems.append("malformed node record")
            continue
        name = node.get("metadata", {}).get("name", "<unknown>")
        status = node.get("status", {})
        ready = any(c.get("type") == "Ready" and c.get("status") == "True"
                    for c in status.get("conditions", []) if isinstance(c, dict))
        if not ready:
            problems.append(f"{name}: NotReady")
        for condition in status.get("conditions", []):
            if condition.get("type") in {"DiskPressure", "MemoryPressure", "PIDPressure"} and condition.get("status") == "True":
                problems.append(f"{name}: {condition['type']}")
        version = status.get("nodeInfo", {}).get("kubeletVersion", "")
        if not version.startswith("v1."):
            problems.append(f"{name}: kubelet version unavailable")
    return problems


def call(*args: str, timeout: int = 20) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=True)
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only acceptance")
    parser.add_argument("--nodes-json", type=Path,
                        help="offline synthetic node input, no cluster contact")
    args = parser.parse_args(argv)
    talos = (ROOT / "config/talos/VERSION").read_text().strip()
    k8s = (ROOT / "config/talos/KUBERNETES_VERSION").read_text().strip()
    if talos != "v1.14.4" or k8s != "v1.37.1":
        print("BLOCKED: unsupported or unreviewed version targets", file=sys.stderr)
        return 2
    try:
        if args.nodes_json:
            nodes = json.loads(args.nodes_json.read_text())
        else:
            # The existing cluster validation script contains additional etcd,
            # LAN and Talos API checks. Run it separately before any apply.
            call("kubectl", "get", "--raw=/readyz")
            nodes = json.loads(call("kubectl", "get", "nodes", "-o", "json"))
            for addr in EXPECTED:
                call("talosctl", "--nodes", addr, "version")
            call("talosctl", "--nodes", EXPECTED[0], "etcd", "status")
            call("kubectl", "get", "storageclass", "-o", "name")
            call("kubectl", "get", "pvc", "-A", "-o", "name")
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("BLOCKED: unable to verify live cluster: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    problems = validate_nodes(nodes)
    for issue in problems:
        print("BLOCKED: " + issue, file=sys.stderr)
    print(json.dumps({
        "readOnly": True,
        "targetTalos": talos,
        "targetKubernetes": k8s,
        "nodeCount": len(nodes.get("items", [])) if isinstance(nodes, dict) else 0,
        "ready": len(problems) == 0,
        "runtimeUpgradePerformed": False,
        "etcdSnapshotVerified": False,
        "csiSmokeVerified": False,
    }, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
