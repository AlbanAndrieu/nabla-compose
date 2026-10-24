#!/usr/bin/env python3
"""Idempotent local SSH tunnel to TrueNAS LiteLLM; no credentials involved.

--check only inspects the listener. --ensure creates a new forward only when
14000 is free and the SSH alias resolves to the approved TrueNAS endpoint.
Never kills an existing process, disables host-key checks, or forwards an agent.
"""
import argparse
import os
import re
import subprocess

FORWARD = "127.0.0.1:14000:127.0.0.1:4000"
ALIAS = "truenas"
ACCEPTED_HOSTS = {"truenas", "172.17.0.24", "albandrieu@172.17.0.24"}


def execute(args, timeout=8):
    try:
        return subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def ssh_alias_valid():
    result = execute(["ssh", "-G", ALIAS])
    if result is None or result.returncode != 0:
        return False
    options = {}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        key, sep, value = line.partition(" ")
        if sep and key in {"hostname", "port", "user"}:
            options[key] = value.strip()
    return (options.get("hostname") == "172.17.0.24"
            and options.get("port") == "9922"
            and options.get("user") == "albandrieu")


def expected_forward(argv):
    """Check the already running SSH process without publishing its argv."""
    for index, token in enumerate(argv):
        spec = None
        if token == "-L" and index + 1 < len(argv):
            spec = argv[index + 1]
        elif token.startswith("-L") and len(token) > 2:
            spec = token[2:]
        if spec == FORWARD and any(x in ACCEPTED_HOSTS for x in argv):
            return True
    return False


def listener_status():
    """Verify an owner-operated ssh -L listener using ss and /proc metadata."""
    result = execute(["ss", "-H", "-ltnp", "( sport = :14000 )"])
    if result is None or result.returncode != 0:
        return "inspection_unavailable"
    lines = result.stdout.decode("utf-8", "replace").splitlines()
    entries = []
    for line in lines:
        columns = line.split()
        if len(columns) >= 4 and re.search(r":14000$", columns[3]):
            entries.append((columns[3], line))
    if not entries:
        return "absent"
    if len(entries) != 1 or entries[0][0] != "127.0.0.1:14000":
        return "occupied_unverified"
    match = re.search(r'users:\(\("ssh",pid=([0-9]+),fd=[0-9]+\)\)', entries[0][1])
    if not match:
        return "occupied_unverified"
    pid = int(match.group(1))
    try:
        if os.stat(f"/proc/{pid}").st_uid != os.geteuid():
            return "occupied_unverified"
        argv = [part.decode("utf-8", "replace") for part in
                open(f"/proc/{pid}/cmdline", "rb").read(16384).split(b"\x00") if part]
        if not argv or os.path.basename(argv[0]) != "ssh":
            return "occupied_unverified"
        return "verified_ssh" if expected_forward(argv) else "occupied_unverified"
    except OSError:
        return "occupied_unverified"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--ensure", action="store_true")
    args = parser.parse_args(argv)
    current = listener_status()
    print("truenas_tunnel=" + current)
    if current == "verified_ssh":
        print("truenas_tunnel_action=reuse")
        return 0
    if current != "absent":
        print("truenas_tunnel_action=blocked")
        return 2
    if args.check:
        print("truenas_tunnel_action=not_started")
        return 2
    if not ssh_alias_valid():
        print("truenas_ssh_alias=unexpected_target_or_port")
        return 2
    print("truenas_ssh_alias=approved_truenas_9922")
    result = execute([
        "ssh", "-f", "-N", "-S", "none", "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ForwardAgent=no", "-o", "ServerAliveInterval=30",
        "-L", FORWARD, ALIAS
    ], timeout=18)
    if result is None or result.returncode != 0:
        print("truenas_tunnel_action=start_failed")
        return 2
    verified = listener_status()
    print("truenas_tunnel_after_start=" + verified)
    return 0 if verified == "verified_ssh" else 2


if __name__ == "__main__":
    raise SystemExit(main())
