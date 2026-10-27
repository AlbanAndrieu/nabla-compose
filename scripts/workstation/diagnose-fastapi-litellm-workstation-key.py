#!/usr/bin/env python3
"""Value-blind, read-only Workstation LiteLLM key provisioning diagnosis.

Runs no /key/generate, no inference, no secret writes. Requires proof of the
Workstation-local running Docker container before sending any network request.
Optionally inventories the exact virtual-key alias with an admin credential
supplied privately in LITELLM_MASTER_KEY. Never prints the API response.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
PROVISIONER = ROOT / "scripts/workstation/provision-fastapi-litellm-keys.py"
spec = importlib.util.spec_from_file_location("litellm_scoped_key_provisioner", PROVISIONER)
assert spec and spec.loader
provisioner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provisioner)
PROXY = "http://127.0.0.1:4000"
ALIAS = "fastapi-sample-upstream"
EXPECTED_CONTAINER = "litellm-litellm-1"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def workstation_identity() -> str:
    """TrueNAS must never be confused with the workstation Docker instance."""
    try:
        mid = subprocess.run(["midclt", "call", "system.version"],
                             timeout=5, capture_output=True, check=False)
    except (OSError, subprocess.TimeoutExpired):
        mid = None
    if mid is not None and mid.returncode == 0 and len(mid.stdout) <= 192:
        v = mid.stdout.decode("ascii", errors="replace").strip().strip('"')
        if re.fullmatch(r"TrueNAS[-_][A-Za-z0-9._+-]{1,100}", v):
            return "truenas_not_workstation"
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=litellm",
             "--filter", "status=running", "--format", "{{.Names}}"],
            timeout=6, check=False, capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "workstation_unverified"
    if result.returncode != 0 or result.stderr or len(result.stdout) > 2048:
        return "workstation_unverified"
    names = result.stdout.decode("ascii", errors="replace").splitlines()
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", n)
           for n in names):
        return "workstation_unverified"
    if names.count(EXPECTED_CONTAINER) == 1 and "litellm" not in names:
        return "workstation_verified"
    return "workstation_container_not_attested"


def key_file_state() -> str:
    path = provisioner.key_file("workstation")
    try:
        provisioner.verify_directory(path.parent)
    except (OSError, ValueError):
        return "unsafe_directory"
    try:
        meta = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unverified"
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid():
        return "unsafe_file"
    if meta.st_mode & 0o077:
        return "unsafe_file"
    return "present_private_unvalidated"


def fetch_json(path: str, *, credential: str = "",
               expect_json: bool = True) -> tuple[str, object | None]:
    headers = {"Accept": "application/json"}
    if credential:
        headers["Authorization"] = "Bearer " + credential
    request = Request(PROXY + path, headers=headers, method="GET")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 200 or response.geturl() != PROXY + path:
                return "unexpected_http", None
            if not expect_json:
                return "http_200", None
            data = response.read(262144 + 1)
            if len(data) > 262144:
                return "unexpected_schema", None
            try:
                return "http_200", json.loads(data)
            except (ValueError, UnicodeError):
                return "unexpected_schema", None
    except HTTPError as error:
        return ("http_" + str(error.code)
                if error.code in (400, 401, 403, 404, 405, 429, 500, 502, 503)
                else "unexpected_http"), None
    except (URLError, OSError, TimeoutError):
        return "unreachable", None


def alias_state() -> str:
    key = os.getenv("LITELLM_MASTER_KEY", "")
    if not key:
        return "admin_credential_not_provided"
    # The caller may have an explicitly configured, non-standard master key.
    # Let the proxy validate it via an authenticated read-only GET.
    if (not key.strip() or len(key) > 4096
            or any(ch in key for ch in ("\\r", "\\n", "\\x00"))
            or key.startswith("Bearer ")):
        return "admin_credential_invalid_transport"
    query = urlencode({"key_alias": ALIAS, "return_full_object": "true",
                       "size": "20", "page": "1"})
    state, data = fetch_json("/key/list?" + query, credential=key)
    if state != "http_200":
        return "key_list_" + state
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        return "key_list_unverified_schema"
    rows = data["keys"]
    if len(rows) > 100:
        return "key_list_unverified_schema"
    exact = [row for row in rows if isinstance(row, dict)
             and row.get("key_alias") == ALIAS]
    if len(exact) > 1:
        return "alias_duplicate"
    if len(exact) == 1:
        return "alias_exists"
    # LiteLLM /key/list uses total_count, not "total".
    # The exact-alias filter and explicit zero count must both be supported.
    # Otherwise, do not treat an empty page as proof of absence.
    if rows == [] and data.get("total_count") == 0:
        return "alias_absent_confirmed"
    return "alias_unverified_not_confirmed_absent"


def report() -> dict:
    identity = workstation_identity()
    result = {
        "schema": "nabla-litellm-scoped-upstream-inventory/v1",
        "host_context": identity,
        "expected_container": EXPECTED_CONTAINER,
        "key_file_state": key_file_state(),
        "proxy_liveliness": "not_checked",
        "alias_state": "not_checked",
        "model_requests_sent": 0,
        "runtime_mutated": False,
        "secret_values_printed": False,
    }
    if identity != "workstation_verified":
        return result
    status, _ = fetch_json("/health/liveliness", expect_json=False)
    # Liveness is HTTP-only and may return non-JSON plain text.
    result["proxy_liveliness"] = status
    if result["proxy_liveliness"] != "http_200":
        return result
    result["alias_state"] = alias_state()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, action="store_true")
    parser.parse_args(argv)
    data = report()
    print(json.dumps(data, sort_keys=True))
    # A successful read-only inventory is not permission to generate a key.
    return 0 if (data["host_context"] == "workstation_verified"
                 and data["proxy_liveliness"] == "http_200") else 2


if __name__ == "__main__":
    raise SystemExit(main())
