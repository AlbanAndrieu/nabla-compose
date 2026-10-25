#!/usr/bin/env python3
"""Resume three existing, stopped TrueNAS Talos VMs; never upgrade/reset Talos."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

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
    if args.start and hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() != 0:
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
        print(f"START: {vm['name']} (existing VM only)")
        try:
            subprocess.run(["midclt", "call", "vm.start", str(vm["id"])],
                           check=True, capture_output=True, text=True, timeout=180)
            post = inventory(json.loads(midclt("vm.query")))
        except (OSError, ValueError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            print(f"BLOCKED: {vm['name']} could not start: {type(exc).__name__}",
                  file=sys.stderr)
            return 1
        if next(item for item in post if item["name"] == vm["name"])["state"] != "RUNNING":
            print(f"BLOCKED: {vm['name']} not RUNNING after vm.start", file=sys.stderr)
            return 1
        print(f"OK: {vm['name']} VM runtime RUNNING, Talos/etcd not yet verified")
    print("NEXT: from workstation run validate-cluster.sh and retained CSI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
