#!/usr/bin/env python3
"""Provision two model-scoped LiteLLM virtual keys without exposing tokens.

Default is offline --check; --apply is a deliberate local operator action.
The TrueNAS endpoint supports SSH loopback forwarding or explicit guarded
native TrueNAS execution.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/fastapi-sample/litellm-key-policy.json"
KEY_DIR = Path.home() / ".local/share/nabla-compose/fastapi-litellm"
TARGETS = ("workstation", "truenas")


def load_policy() -> dict:
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["workload"] == "fastapi-sample"
    assert data["budget"]["requested_eur_max"] == 10
    assert data["budget"]["litellm_usd_lifetime_cap"] == 8
    assert data["budget"]["budget_duration"] is None
    assert data["limits"] == {
        "rpm_limit": 5, "tpm_limit": 15000, "max_parallel_requests": 1,
    }
    assert data["keys"]["workstation"]["models"] == ["qwen"]
    assert data["keys"]["truenas"]["models"] == ["fastapi-qwen"]
    assert data["keys"]["workstation"]["endpoint"] == "http://127.0.0.1:4000"
    assert data["keys"]["truenas"]["endpoint"] == "http://127.0.0.1:14000"
    return data


def verify_directory(path: Path) -> None:
    """No group-writable components or symlinks under the user's home."""
    home = Path.home().resolve()
    relative = path.relative_to(home)
    current = home
    for part in relative.parts:
        current /= part
        try:
            st = current.lstat()
        except FileNotFoundError:
            break
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise ValueError("unsafe key directory hierarchy")
        if st.st_mode & 0o022:
            raise ValueError("key directory hierarchy is writable by others")
    if path.exists() and path.stat().st_mode & 0o077:
        raise ValueError("key directory must be owner-only")


def key_file(target: str) -> Path:
    return KEY_DIR / (target + ".key")


def payload(policy: dict, target: str) -> dict:
    entry = policy["keys"][target]
    return {
        "key_alias": entry["key_alias"],
        "models": entry["models"],
        "max_budget": policy["budget"]["litellm_usd_lifetime_cap"],
        "budget_duration": None,  # no reset / lifetime cap
        **policy["limits"],
        "metadata": {"workload": "fastapi-sample", "environment": "truenas-staging",
                     "managed_by": "nabla-compose", "scope": target},
    }


class NoRedirect(HTTPRedirectHandler):
    """Never forward the admin Authorization header across redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require_native_truenas() -> None:
    """Confirm local TrueNAS middleware before using its loopback proxy."""
    try:
        response = subprocess.run(
            ["midclt", "call", "system.version"],
            check=False, capture_output=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("native TrueNAS host is not verified") from None
    if response.returncode or response.stderr or len(response.stdout) > 192:
        raise ValueError("native TrueNAS host is not verified")
    version = response.stdout.decode("ascii", errors="replace").strip().strip('"')
    if re.fullmatch(r"TrueNAS[-_][A-Za-z0-9._+-]{1,100}", version) is None:
        raise ValueError("native TrueNAS host is not verified")


def provision(policy: dict, target: str, output: Path, *,
              endpoint_override: str | None = None) -> None:
    """Reserve the secret destination before calling /key/generate."""
    entry = policy["keys"][target]
    endpoint = endpoint_override or entry["endpoint"]
    if endpoint not in ("http://127.0.0.1:4000", "http://127.0.0.1:14000"):
        raise ValueError("proxy management endpoint must remain loopback")
    master = os.getenv(entry["master_env"], "")
    if not master.startswith("sk-"):
        raise ValueError("dedicated proxy administrator secret missing")
    if os.geteuid() == 0:
        raise ValueError("must run as the unprivileged operator on the selected host")
    verify_directory(output.parent)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    verify_directory(output.parent)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, 0o600)
    created = False
    try:
        request = Request(
            endpoint + "/key/generate",
            method="POST",
            headers={"Authorization": "Bearer " + master,
                     "Content-Type": "application/json"},
            data=json.dumps(payload(policy, target)).encode(),
        )
        # No redirect to a non-loopback URL and no token in command arguments.
        # HTTP loopback only; a TrueNAS tunnel or verified native host is required.
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            if response.geturl() != endpoint + "/key/generate":
                raise ValueError("key-generation endpoint redirected")
            result = json.load(response)
        key = result.get("key") if isinstance(result, dict) else None
        if not isinstance(key, str) or not key.startswith("sk-"):
            raise ValueError("unusable LiteLLM key response")
        # LiteLLM currently returns some budgets in key_info; fail closed
        # when server explicitly reports a different max_budget.
        info = result.get("key_info") if isinstance(result.get("key_info"), dict) else result
        if "max_budget" in info and info["max_budget"] != 8:
            raise ValueError("proxy ignored required virtual-key budget")
        stream = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        with stream:
            stream.write(key + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        fd = -1
        created = True
    finally:
        if fd >= 0:
            os.close(fd)
        if not created:
            output.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument(
        "--native-truenas", action="store_true",
        help="on TrueNAS only: use the native proxy on 127.0.0.1:4000 "
             "instead of the workstation SSH tunnel on 127.0.0.1:14000",
    )
    args = parser.parse_args()
    try:
        policy = load_policy()
        endpoint_override = None
        if args.native_truenas:
            if args.target != "truenas":
                raise ValueError("native TrueNAS mode cannot issue workstation keys")
            require_native_truenas()
            endpoint_override = "http://127.0.0.1:4000"
        output = key_file(args.target)
        verify_directory(output.parent)
        if output.is_symlink():
            raise ValueError("symlink destination forbidden")
        if output.exists():
            st = output.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
                raise ValueError("existing key file permissions are not private")
            print("status=already_provisioned; no mutation or key read")
            return 0
        if args.check:
            print(f"status=not_provisioned target={args.target} model={policy['keys'][args.target]['models'][0]}")
            print("lifetime_budget_usd=8 requested_ceiling_eur=10 reset=never")
            print("configuration_only=true network_calls=0")
            return 0
        provision(policy, args.target, output, endpoint_override=endpoint_override)
        print(f"status=created target={args.target} model={policy['keys'][args.target]['models'][0]}")
        print("key_location=private_operator_file mode=0600; key_value=suppressed")
        print("NEXT: transfer to Vaultwarden; verify /key/info, database and model allowlist")
        return 0
    except (OSError, ValueError, KeyError, AssertionError, HTTPError, URLError,
            TimeoutError, json.JSONDecodeError):
        print("BLOCKED: configuration, transport or secure-storage failure", file=sys.stderr)
        print("If proxy created a key before failure, revoke the orphan before retrying", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
