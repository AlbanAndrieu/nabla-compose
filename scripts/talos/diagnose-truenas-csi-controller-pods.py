#!/usr/bin/env python3
"""Read-only ownership and readiness check for TrueNAS CSI controller Pods."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

NAMESPACE = "truenas-csi"
DEPLOYMENT = "truenas-csi-controller"


def kubectl(*args: str) -> object:
    result = subprocess.run(
        ["kubectl", "--request-timeout=10s", "-n", NAMESPACE, "get", *args,
         "-o", "json"],
        check=True, capture_output=True, text=True, timeout=25,
    )
    return json.loads(result.stdout)


def assess(deploy: object, replicas: object, pods: object) -> dict:
    if not isinstance(deploy, dict) or not isinstance(replicas, dict) or not isinstance(pods, dict):
        raise ValueError("Malformed CSI inventory")
    desired = deploy.get("spec", {}).get("replicas")
    available = deploy.get("status", {}).get("availableReplicas", 0)
    if not isinstance(desired, int) or not isinstance(available, int):
        raise ValueError("Invalid deployment replica counts")
    rs_rows = replicas.get("items", [])
    pod_rows = pods.get("items", [])
    if not isinstance(rs_rows, list) or not isinstance(pod_rows, list):
        raise ValueError("Malformed ReplicaSet/Pod list")
    active_rs = {
        row.get("metadata", {}).get("name")
        for row in rs_rows if isinstance(row, dict)
        and row.get("spec", {}).get("replicas", 0) > 0
    }
    if len(active_rs) != 1 or None in active_rs:
        return {"status": "UNVERIFIED", "reason": "ambiguous_active_replicaset"}
    active = next(iter(active_rs))
    running = []
    failed = []
    for pod in pod_rows:
        if not isinstance(pod, dict):
            continue
        meta = pod.get("metadata", {})
        phase = pod.get("status", {}).get("phase", "Unknown")
        owners = [r.get("name") for r in meta.get("ownerReferences", [])
                  if isinstance(r, dict) and r.get("kind") == "ReplicaSet"
                  and r.get("controller") is True]
        if owners != [active]:
            continue
        name = meta.get("name", "UNKNOWN")
        statuses = pod.get("status", {}).get("containerStatuses") or []
        ready = phase == "Running" and len(statuses) == 5 and all(
            isinstance(c, dict) and c.get("ready") is True for c in statuses
        )
        if ready:
            running.append(name)
        elif phase in ("Failed", "Succeeded"):
            failed.append({"name": name, "phase": phase})
    service_ready = desired == 1 and available == 1 and len(running) == 1
    return {
        "status": "CONTROLLER_READY_WITH_TERMINATED_PODS" if service_ready and failed
                  else "CONTROLLER_READY" if service_ready else "UNVERIFIED",
        "activeReplicaSet": active,
        "desired": desired,
        "available": available,
        "readyPodCount": len(running),
        "terminatedPods": failed,
        "next": "inspect_exact_pod_owner_and_events_before_optional_cleanup" if failed
                else "no_pod_cleanup_indicated",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        result = assess(
            kubectl("deployment", DEPLOYMENT),
            kubectl("replicasets", "-l", "app=truenas-csi-controller"),
            kubectl("pods", "-l", "app=truenas-csi-controller"),
        )
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("UNVERIFIED: CSI inventory unavailable: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    print("READ_ONLY: no Pod/ReplicaSet/Deployment deletion, no PVC mutation")
    return 0 if result["status"].startswith("CONTROLLER_READY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
