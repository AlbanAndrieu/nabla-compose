#!/usr/bin/env python3
"""Observe GPG/PCSC processes, SSH-agent and recovery tool metadata only.

Does not open secret files, start/stop daemons, query YubiKeys, enumerate
account names, request PINs, list credentials or initiate cryptography.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

TOOLS = ("pg_restore", "pg_dump", "psql", "initdb", "pg_ctl", "age", "sops", "gpg", "ssh-add")


def process_state(name: str, uid: int | None = None) -> str:
    """Observe process existence without reading process arguments or identifiers."""
    if name not in {"scdaemon", "pcscd"}:
        return "UNKNOWN"
    if not shutil.which("pgrep"):
        return "TOOL_MISSING"
    command = ["pgrep", "-x"]
    if uid is not None:
        command += ["-u", str(uid)]
    command += [name]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "UNKNOWN"
    if result.returncode == 0:
        return "PROCESS_PRESENT_UNVERIFIED"
    if result.returncode == 1:
        return "PROCESS_NOT_OBSERVED"
    return "UNKNOWN"


def ssh_agent_state() -> str:
    """Query only public identity presence, with all ssh-add output discarded."""
    raw = os.environ.get("SSH_AUTH_SOCK", "")
    if not raw:
        return "SOCKET_NOT_CONFIGURED"
    if "\0" in raw or len(raw) > 4096 or not Path(raw).is_absolute():
        return "UNKNOWN"
    try:
        meta = Path(raw).lstat()  # Refuse links, never open the socket ourselves.
        if not stat.S_ISSOCK(meta.st_mode) or meta.st_uid != os.getuid():
            return "SOCKET_UNTRUSTED"
    except FileNotFoundError:
        return "SOCKET_NOT_FOUND"
    except (OSError, ValueError):
        return "UNKNOWN"
    if not shutil.which("ssh-add"):
        return "TOOL_MISSING"
    try:
        result = subprocess.run(["ssh-add", "-l"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "UNKNOWN"
    if result.returncode == 0:
        return "PUBLIC_IDENTITIES_PRESENT_UNVERIFIED"
    if result.returncode == 1:
        return "NO_IDENTITIES_OR_AGENT"
    return "UNKNOWN"


def snapshot() -> dict:
    return {
        "status": "NO-GO",
        "mode": "HOST_DEPENDENCIES_METADATA_ONLY",
        "scdaemon": process_state("scdaemon", uid=os.getuid()),
        "pcscd": process_state("pcscd"),
        "ssh_agent": ssh_agent_state(),
        "recovery_tools": {name: "INSTALLED_UNVERIFIED" if shutil.which(name) else "MISSING"
                           for name in TOOLS},
        "openpgp_card_access_verified": False,
        "postgres_restore_verified": False,
        "ssh_fido_login_verified": False,
        "escrow_restore_verified": False,
        "hardware_mutation_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("No arguments supported", file=sys.stderr)
        return 2
    print(json.dumps(snapshot(), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
