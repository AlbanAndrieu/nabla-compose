#!/usr/bin/env python3
"""Run LiteLLM key operations on TrueNAS, locally or over SSH.

The canonical TrueNAS checkout uses local Docker. A workstation checkout
uses the existing SSH alias. No secret enters command arguments or stdout.
"""
import argparse
from pathlib import Path
import subprocess
import sys

TRUENAS_ROOT = Path("/mnt/cpool/compose/nabla-compose")
ROOT = Path(__file__).resolve().parents[2]
PROVISIONER = ROOT / "scripts/truenas/provision-openclaw-litellm-keys.py"
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "truenas")


def execution_target(root=ROOT):
    """Select target by canonical checkout, not a hostname or a TCP port."""
    return "truenas_local" if root.resolve() == TRUENAS_ROOT else "workstation_ssh"


def build_command(mode, target):
    if mode not in ("plan", "apply", "status", "quota-audit", "update-scope"):
        raise ValueError("unsupported_mode")
    arguments = {"plan": (), "apply": ("--apply",), "status": ("--status",),
                 "quota-audit": ("--quota-audit",), "update-scope": ("--update-scope",)}[mode]
    if target == "truenas_local":
        return ["sudo", "-n", "python3", str(PROVISIONER), *arguments]
    if target == "workstation_ssh":
        return [*SSH, "sudo -n python3 -" + (" " + " ".join(arguments) if arguments else "")]
    raise ValueError("unsupported_target")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "apply", "status", "quota-audit", "update-scope"), default="plan")
    args = parser.parse_args(argv)
    if not PROVISIONER.is_file():
        print("provisioner=missing")
        return 2
    target = execution_target()
    print("execution_target=" + target, flush=True)
    command = build_command(args.mode, target)
    try:
        if target == "truenas_local":
            result = subprocess.run(command, check=False)
        else:
            with PROVISIONER.open("rb") as source:
                result = subprocess.run(command, stdin=source, check=False)
    except OSError:
        print("provisioner_execution=unavailable")
        return 2
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
