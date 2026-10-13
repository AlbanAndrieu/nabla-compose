#!/usr/bin/env python3
"""Hermes TrueNAS POC preflight: read-only, never prints credential values."""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

DEFAULT_ENV = Path("/mnt/cpool/secrets/runtime/hermes/.env.secrets")
DEFAULT_STATE = Path("/mnt/cpool/hermes/poc")
REQUIRED = {"HERMES_LITELLM_API_KEY"}
BOTS = {
    "TELEGRAM_BOT_TOKEN": "TELEGRAM_ALLOWED_USERS",
    "DISCORD_BOT_TOKEN": "DISCORD_ALLOWED_USERS",
}
UNSAFE_TRUE = {
    "GATEWAY_ALLOW_ALL_USERS",
    "TELEGRAM_ALLOW_ALL_USERS",
    "DISCORD_ALLOW_ALL_USERS",
    "HERMES_YOLO_MODE",
}
DIGEST = re.compile(r"^nousresearch/hermes-agent@sha256:[0-9a-f]{64}$")


def parse_names(path: Path) -> dict[str, str]:
    # No 'source', eval, shell interpolation or output of the values.
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError("Malformed environment materialization")
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in result:
            raise ValueError("Invalid or duplicated environment key")
        result[name] = value.strip()
    return result


def validate(env: Path, state: Path, image: str, api: bool) -> list[str]:
    errors = []
    if not DIGEST.fullmatch(image):
        errors.append("Image must be pinned to nousresearch/hermes-agent@sha256:<digest>")
    try:
        secret_available = env.is_file() and not env.is_symlink()
        state_available = state.is_dir() and not state.is_symlink()
    except PermissionError:
        errors.append("Cannot inspect Hermes POC paths: run read-only check with sudo")
        return errors
    if not secret_available:
        errors.append("Dedicated runtime secret file missing or unsafe symlink")
        return errors
    if not state_available:
        errors.append("Dedicated isolated POC state directory missing or unsafe symlink")
        return errors
    try:
        e_stat = env.stat()
        s_stat = state.stat()
    except PermissionError:
        errors.append("Cannot stat Hermes POC paths: run read-only check with sudo")
        return errors
    if stat.S_IMODE(e_stat.st_mode) != 0o600 or e_stat.st_uid != 0:
        errors.append("Runtime secret file must be root-owned mode 0600")
    if stat.S_IMODE(s_stat.st_mode) & 0o077:
        errors.append("POC state directory must not be accessible to group/others")
    if s_stat.st_uid != 10000:
        errors.append("POC state must be owned by Hermes UID 10000")
    try:
        data = parse_names(env)
    except (OSError, UnicodeError, ValueError):
        errors.append("Could not validate environment keys")
        return errors
    for name in REQUIRED:
        if not data.get(name):
            errors.append("Required environment key missing (name only): " + name)
    if not any(data.get(bot) for bot in BOTS):
        errors.append("No Telegram/Discord bot identity present")
    for bot, allowlist in BOTS.items():
        if data.get(bot):
            allowed_ids = data.get(allowlist, "")
            if not allowed_ids:
                errors.append("Missing allowlist: " + allowlist)
            elif not re.fullmatch(r"[0-9]{5,22}(,[0-9]{5,22})*", allowed_ids):
                errors.append("Allowlist must contain only numeric user IDs: " + allowlist)
    # Global cross-platform users, Discord channel/role grants and permissive
    # pairing can bypass a seemingly narrow platform-specific user allowlist.
    for name in ("GATEWAY_ALLOWED_USERS", "DISCORD_ALLOWED_CHANNELS",
                 "DISCORD_ALLOWED_ROLES"):
        if data.get(name):
            errors.append("Non-owner identity surface forbidden in PoC: " + name)
    if any(data.get(k, "").strip("\"' ").lower() in ("true", "1", "yes", "on") for k in UNSAFE_TRUE):
        errors.append("Unsafe allow-all or YOLO setting enabled")
    if api and (not data.get("API_SERVER_KEY") or len(data["API_SERVER_KEY"]) < 32):
        errors.append("API option requires dedicated 32+ character API_SERVER_KEY")
    if set(data).intersection({"LITELLM_MASTER_KEY", "BW_SESSION", "BW_CLIENTSECRET", "TRUENAS_API_KEY"}):
        errors.append("Privileged master/vault/host secret key names forbidden in Hermes")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only validation (default)")
    parser.add_argument("--api", action="store_true", help="validate optional interservice API credential")
    args = parser.parse_args()
    problems = validate(
        Path(os.environ.get("HERMES_POC_SECRET_FILE", DEFAULT_ENV)),
        Path(os.environ.get("HERMES_POC_STATE_DIR", DEFAULT_STATE)),
        os.environ.get("HERMES_IMAGE_REF", ""),
        args.api,
    )
    if problems:
        for msg in problems:
            print("FAIL: " + msg, file=sys.stderr)
        print("hermes_poc_preflight=blocked")
        return 1
    print("hermes_poc_preflight=ready_metadata_only")
    print("WARNING: egress firewall/TrueNAS container UID and unique bot session require live verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
