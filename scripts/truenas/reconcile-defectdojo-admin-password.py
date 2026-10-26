#!/usr/bin/env python3
"""Check or reconcile an EXISTING DefectDojo Django admin password from runtime secrets.

Read-only by default. On explicit apply, update only the existing Django
password hash. Never create accounts, restart containers, or print secrets.
Vaultwarden parity is separate and must be verified after an apply.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

SOURCE = Path("/mnt/cpool/secrets/runtime/defectdojo/.env.secrets")
CONTAINER = "defectdojo-uwsgi"
ACK = "I_APPROVE_EXISTING_DEFECTDOJO_ADMIN_PASSWORD_SYNC"
REQUIRED = ("DD_ADMIN_USER", "DD_ADMIN_PASSWORD")
MAX_BYTES = 32 * 1024

DJANGO = r"""
import json, sys
from django.contrib.auth import get_user_model
from django.db import transaction
try:
    request = json.loads(sys.stdin.read(32769))
    login, secret, operation = request["username"], request["password"], request["operation"]
    U = get_user_model()
    qs = U.objects.filter(username=login)
    if qs.count() != 1:
        status = "ACCOUNT_NOT_UNIQUE_OR_ABSENT"
    else:
        user = qs.first()
        if not (user.is_active and user.is_staff and user.is_superuser):
            status = "ACCOUNT_NOT_ACTIVE_ADMIN"
        elif user.check_password(secret):
            status = "PASSWORD_MATCH"
        elif operation == "check":
            status = "PASSWORD_MISMATCH"
        elif operation == "apply":
            with transaction.atomic():
                user = U.objects.select_for_update().get(pk=user.pk)
                if not (user.is_active and user.is_staff and user.is_superuser):
                    status = "ACCOUNT_NOT_ACTIVE_ADMIN"
                elif user.check_password(secret):
                    status = "PASSWORD_MATCH"
                else:
                    user.set_password(secret)
                    user.save(update_fields=["password"])
                    status = "PASSWORD_UPDATED"
        else:
            status = "UNVERIFIED"
except Exception:
    status = "DJANGO_QUERY_FAILED"
print(json.dumps({"state": status}, sort_keys=True))
"""


def parse_runtime_secret(path: Path = SOURCE) -> dict[str, str]:
    if path.is_symlink():
        raise ValueError("SOURCE_SYMLINK")
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid != 0 or info.st_gid != 0 or
            stat.S_IMODE(info.st_mode) != 0o600 or
            not 0 < info.st_size <= MAX_BYTES):
        raise ValueError("SOURCE_METADATA_INVALID")
    data = path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for line in data.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if "=" not in clean:
            raise ValueError("SOURCE_FORMAT_INVALID")
        key, value = clean.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("SOURCE_FORMAT_INVALID")
        if key in found:
            raise ValueError("SOURCE_DUPLICATE_KEY")
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"'):
            if value[-1] != value[0]:
                raise ValueError("SOURCE_FORMAT_INVALID")
            decoded = shlex.split(value, posix=True)
            if len(decoded) != 1:
                raise ValueError("SOURCE_FORMAT_INVALID")
            value = decoded[0]
        found[key] = value
    if not all(found.get(key) for key in REQUIRED):
        raise ValueError("SOURCE_ADMIN_CREDENTIAL_MISSING")
    if found["DD_ADMIN_USER"] != "admin":
        # This existing installation is proven to have the admin account.
        # Do not accidentally create/sync the declarative 'nabla' bootstrap.
        raise ValueError("SOURCE_USERNAME_NOT_EXISTING_ADMIN")
    if len(found["DD_ADMIN_PASSWORD"]) < 12 or len(found["DD_ADMIN_PASSWORD"]) > 512:
        raise ValueError("SOURCE_PASSWORD_LENGTH_INVALID")
    return {key: found[key] for key in REQUIRED}


def run_django(credentials: dict[str, str], operation: str) -> str:
    payload = json.dumps({
        "username": credentials["DD_ADMIN_USER"],
        "password": credentials["DD_ADMIN_PASSWORD"],
        "operation": operation,
    })
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "python", "manage.py", "shell", "-c", DJANGO],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=35,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "DJANGO_UNAVAILABLE"
    if proc.returncode != 0:
        return "DJANGO_UNAVAILABLE"
    # Django versions may emit startup banners; use only the last bounded JSON.
    try:
        response = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError):
        return "DJANGO_RESPONSE_UNVERIFIED"
    state = response.get("state") if isinstance(response, dict) else None
    allowed = {
        "ACCOUNT_NOT_UNIQUE_OR_ABSENT", "ACCOUNT_NOT_ACTIVE_ADMIN",
        "PASSWORD_MATCH", "PASSWORD_MISMATCH", "PASSWORD_UPDATED",
        "DJANGO_QUERY_FAILED",
    }
    return state if state in allowed else "DJANGO_RESPONSE_UNVERIFIED"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--acknowledge")
    args = p.parse_args(argv)
    if os.geteuid() != 0:
        p.error("root required for protected runtime secret read")
    if args.apply and args.acknowledge != ACK:
        p.error("explicit acknowledgement required for Django password update")
    try:
        credential = parse_runtime_secret()
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({
            "component": "defectdojo_admin_password",
            "status": "BLOCKED",
            "category": str(exc) if isinstance(exc, ValueError) and
                        str(exc).startswith("SOURCE_") else type(exc).__name__,
        }))
        return 2
    state = run_django(credential, "apply" if args.apply else "check")
    print(json.dumps({
        "component": "defectdojo_admin_password",
        "mode": "apply" if args.apply else "check",
        "state": state,
        "vaultwarden_parity": "NOT_VERIFIED",
        "restarted": False,
    }, sort_keys=True))
    if state in ("PASSWORD_MATCH", "PASSWORD_UPDATED"):
        return 0
    return 1 if state == "PASSWORD_MISMATCH" else 2


if __name__ == "__main__":
    sys.exit(main())
