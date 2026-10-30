#!/usr/bin/env python3
"""Non-secret host fingerprint for homelab diagnostic routing."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess


def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=4, check=False)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detect(home=None):
    home = home or Path.home()
    version = run(["midclt", "call", "system.version"])
    if version.startswith("TrueNAS-") or version.startswith('"TrueNAS-'):
        return "truenas"
    # A workstation marker is required; generic Linux != workstation.
    cfg = home / ".openclaw" / "openclaw.json"
    unit = run(["systemctl", "--user", "show", "openclaw-gateway.service",
                "-p", "LoadState", "--value"])
    if cfg.is_file() and unit in ("loaded", "masked"):
        return "workstation"
    return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", action="store_true", help="Print only the host classification")
    args = parser.parse_args(argv)
    host = detect()
    if args.kind:
        print(host)
    else:
        print("host_context=" + host)
        print("cross_host_openclaw_probe=" + ("not_applicable" if host == "truenas"
                                                else "workstation_only" if host == "workstation"
                                                else "blocked_unknown_host"))
    return 0 if host != "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
