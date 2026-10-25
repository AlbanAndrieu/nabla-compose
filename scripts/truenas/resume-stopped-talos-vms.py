#!/usr/bin/env python3
"""Resume three existing, stopped TrueNAS Talos VMs; never upgrade/reset Talos."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

VM_NAMES = ("taloscp01", "taloswk01", "taloswk02")
ACK = "I_ACCEPT_STARTING_EXISTING_TALOS_VMS"


def midclt(*parts: str, timeout: int = 90) -> str:
    result = subprocess.run(["midclt", "call", *parts], check=True,
                            capture_output=True, text=True, timeout=timeout)
    return result.stdout


def inventory(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("unexpected TrueNAS vm.query result")
    selected = []
    for name in VM_NAMES:
        matches = [vm for vm in payload
                   if isinstance(vm, dict) and vm.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"{name}: missing or duplicate VM")
        vm = matches[0]
        state = vm.get("status", {}).get("state", "UNKNOWN")
        vid = vm.get("id")
        if not isinstance(vid, int) or isinstance(vid, bool) or vid < 1:
            raise ValueError(f"{name}: unexpected VM ID")
        if state not in ("STOPPED", "RUNNING"):
            raise ValueError(f"{name}: unsafe VM state")
        selected.append({"name": name, "id": vid, "state": state,
                         "autostart": vm.get("autostart") is True})
    return selected



def wait_for_vm_state(name: str, expected: str = "RUNNING",
                      attempts: int = 5, delay: int = 4) -> str:
    """Re-read middleware state. Never retry the mutating vm.start call.

    A timed-out vm.start may still be completing asynchronously. A STOPPED
    result does not prove it is safe to start again.
    """
    latest = "UNKNOWN"
    for attempt in range(attempts):
        try:
            raw = json.loads(midclt("vm.query", timeout=20))
            matches = [vm for vm in raw if isinstance(vm, dict)
                       and vm.get("name") == name]
            if len(matches) != 1:
                raise ValueError("VM inventory changed")
            latest = matches[0].get("status", {}).get("state", "UNKNOWN")
            if latest == expected:
                return latest
        except (OSError, ValueError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired, json.JSONDecodeError):
            latest = "UNKNOWN"
        if attempt + 1 < attempts:
            time.sleep(delay)
    return latest


def start_and_observe(vm: dict) -> bool:
    """Issue at most one start request; observe even after a timeout/error."""
    name = vm["name"]
    print(f"START: {name} (one middleware request, existing VM only)", flush=True)
    request_problem = None
    try:
        subprocess.run(["midclt", "call", "vm.start", str(vm["id"])],
                       check=True, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        request_problem = type(exc).__name__

    state = wait_for_vm_state(name)
    if state == "RUNNING":
        if request_problem:
            print(f"WARN: {name} vm.start={request_problem}; "
                  "subsequent vm.query confirms RUNNING")
        print(f"OK: {name} VM runtime RUNNING, Talos/etcd not yet verified")
        return True

    print(f"UNVERIFIED: {name} vm.start={request_problem or 'returned'} "
          f"current_state={state}; do NOT retry until middleware job settles",
          file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--start", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--query-json", type=Path, help="offline --check fixture only")
    args = parser.parse_args(argv)
    if args.start and args.acknowledge != ACK:
        parser.error("--start needs exact --acknowledge " + ACK)
    if args.query_json and args.start:
        parser.error("synthetic query forbidden with --start")
    if args.check and args.acknowledge:
        parser.error("--acknowledge is only valid with --start")
    if args.start and hasattr(os, "geteuid") and os.geteuid() != 0:
        parser.error("--start requires root on TrueNAS")
    try:
        raw = args.query_json.read_text() if args.query_json else midclt("vm.query")
        vms = inventory(json.loads(raw))
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("BLOCKED: VM inventory unavailable or unexpected: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    for vm in vms:
        print(f"{vm['name']} id={vm['id']} state={vm['state']} "
              f"autostart={str(vm['autostart']).lower()}")
    if args.check:
        print("READ_ONLY: no Talos upgrades, VM startups or Kubernetes mutations")
        return 0
    for vm in vms:
        if vm["state"] == "RUNNING":
            print(f"SKIP: {vm['name']} already RUNNING")
            continue
        if not start_and_observe(vm):
            return 1
    print("NEXT: from workstation run validate-cluster.sh and retained CSI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
