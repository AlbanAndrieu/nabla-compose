#!/usr/bin/env python3
"""Retarget only the existing OpenClaw user service's Node executable.

Fixes the updater's \`preflight-node-runtime-incompatible\` without creating
another installation, migrating state, restarting Gateway, or taking backups.
The managed OpenClaw package root stays unchanged until \`openclaw update\`.
Never expose config, EnvironmentFile, tokens, or raw systemctl output.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import subprocess

UNIT = "openclaw-gateway.service"
RELEASE = "24.22.1"
DROPIN = "25-nabla-node-runtime-compat.conf"
ENTRY_PATTERN = re.compile(
    r"([^\s;{}\"']+)/lib/node_modules/openclaw/(?:dist/index\.js|openclaw\.mjs)"
)
NODE_PATTERN = re.compile(r"/node/(\d+\.\d+\.\d+)/bin/node")


def home():
    return Path.home()


def node_bin():
    return home() / ".local/share/mise/installs/node" / RELEASE / "bin/node"


def override_path():
    return home() / ".config/systemd/user" / (UNIT + ".d") / DROPIN


def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=12, check=False)
        return result.returncode, result.stdout[:32768]
    except (OSError, subprocess.TimeoutExpired):
        return 127, b""


def safe_file(path):
    try:
        st = path.lstat()
        return stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
    except OSError:
        return False


def node_supported():
    target = node_bin()
    if not safe_file(target):
        return False
    result, out = command([str(target), "--version"])
    return result == 0 and out.strip() == ("v" + RELEASE).encode()


def unit_active():
    result, out = command(["systemctl", "--user", "is-active", UNIT])
    return result == 0 and out.strip() == b"active"


def unit_exec():
    result, out = command(["systemctl", "--user", "show", UNIT, "-p", "ExecStart", "--value"])
    if result or not out:
        return None
    raw = out.decode("utf-8", "replace")
    found = ENTRY_PATTERN.findall(raw)
    if len(found) != 1:
        return None
    if "--max-old-space-size=16053" not in raw or "gateway --port 18789" not in raw:
        return None
    owner = Path(found[0])
    expected = home() / ".local/share/mise/installs/node/24.18.1"
    if owner != expected:
        return None
    if not safe_file(owner / "lib/node_modules/openclaw/openclaw.mjs"):
        return None
    if not (
        "path=/usr/bin/node" in raw or
        str(node_bin()) in raw
    ):
        return None
    return owner, raw


def prepared_unit():
    state = unit_exec()
    if state is None:
        return None
    owner, _ = state
    if not node_supported():
        return None
    # Never interpolate unescaped or expansion-sensitive path strings into
    # systemd unit syntax. This script supports the known Ubuntu layout only.
    for p in (node_bin(), owner):
        if any(ch.isspace() or ch in "%\\\"$;" for ch in str(p)):
            return None
    entry = owner / "lib/node_modules/openclaw/openclaw.mjs"
    return ("[Service]\nExecStart=\nExecStart=" + str(node_bin()) +
            " --max-old-space-size=16053 " + str(entry) +
            " gateway --port 18789\n")


def apply():
    if unit_active():
        print("node_runtime_switch=blocked_gateway_active")
        return 2
    body = prepared_unit()
    if body is None:
        print("node_runtime_switch=blocked_unverified_service_or_node")
        return 2
    target = override_path()
    if target.is_symlink():
        print("node_runtime_switch=blocked_existing_override")
        return 2
    if target.exists():
        try:
            if target.read_text(encoding="utf-8") == body:
                info = unit_exec()
                if info is not None and str(node_bin()) in info[1]:
                    print("node_runtime_switch=already_applied")
                    return 0
                print("node_runtime_switch=blocked_override_not_effective")
                return 2
        except OSError:
            pass
        print("node_runtime_switch=blocked_existing_override")
        return 2
    try:
        parent = target.parent
        # Create only the dedicated directories with 0700 even under
        # umask 0002. Refuse pre-existing symlinks and group-writable
        # parents; do not chmod unrelated systemd settings.
        config = home() / ".config"
        systemd = config / "systemd"
        user = systemd / "user"
        for directory in (config, systemd, user, parent):
            if not directory.exists() and not directory.is_symlink():
                directory.mkdir(mode=0o700)
            st = directory.lstat()
            if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o022):
                print("node_runtime_switch=blocked_unsafe_unit_directory")
                return 2
        with target.open("x", encoding="utf-8") as writer:
            os.fchmod(writer.fileno(), 0o600)
            writer.write(body)
            writer.flush()
            os.fsync(writer.fileno())
        rc, _ = command(["systemctl", "--user", "daemon-reload"])
        if rc:
            raise OSError("reload")
        verified = unit_exec()
        if verified is None or str(node_bin()) not in verified[1]:
            raise OSError("unit_owner_mismatch")
    except (OSError, ValueError):
        try:
            if target.is_file() and not target.is_symlink() and target.read_text() == body:
                target.unlink()
                command(["systemctl", "--user", "daemon-reload"])
        except OSError:
            pass
        print("node_runtime_switch=failed_reverted_override_if_owned")
        return 2
    print("node_runtime_switch=applied")
    print("node_runtime_target=" + RELEASE)
    print("gateway_restart_performed=false")
    print("package_root_changed=false")
    print("backup_created=false")
    return 0


def plan():
    info = unit_exec()
    print("node_runtime_target=" + RELEASE)
    print("node_runtime_compatible=" + ("yes" if node_supported() else "no"))
    print("gateway_service_owner=" + ("verified" if info else "unverified"))
    print("gateway_running=" + ("yes" if unit_active() else "no"))
    print("package_root_policy=preserve_existing")
    print("override_present=" + ("yes" if override_path().exists() else "no"))
    print("backup_requested=false")
    return 0 if info and node_supported() else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true")
    action.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    return plan() if args.plan else apply()


if __name__ == "__main__":
    raise SystemExit(main())
