#!/usr/bin/env python3
"""Read-only TrueNAS LiteLLM -> Workstation LiteLLM auth preflight.

Does NOT send protected model requests, call models or read credential values.
Uses a fixed Docker container and two fixed environment variable *names*.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

PROXY = "http://172.17.0.57:4000"
# The command is a constant and never interpolates user input or secret values.
PRESENCE_SCRIPT = (
    "import os; "
    "names=('LITELLM_IDE_API_KEY','LITELLM_FASTAPI_WORKSTATION_API_KEY'); "
    "print('\\n'.join(n+'='+('present' if bool(os.getenv(n)) else 'absent') for n in names))"
)
KEYS = ("LITELLM_IDE_API_KEY", "LITELLM_FASTAPI_WORKSTATION_API_KEY")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_container() -> dict:
    try:
        cp = subprocess.run(
            ["docker", "exec", "litellm", "python3", "-c", PRESENCE_SCRIPT],
            capture_output=True, check=False, timeout=8
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"container": "unavailable", "key_presence": "unverified"}
    if cp.returncode != 0 or len(cp.stdout) > 512 or cp.stderr:
        return {"container": "unavailable", "key_presence": "unverified"}
    lines = cp.stdout.decode("ascii", errors="replace").splitlines()
    expected = {name + "=present" for name in KEYS} | {name + "=absent" for name in KEYS}
    if len(lines) != len(KEYS) or any(line not in expected for line in lines):
        return {"container": "unexpected_schema", "key_presence": "unverified"}
    state = {line.split("=")[0]: line.split("=")[1] for line in lines}
    if set(state) != set(KEYS):
        return {"container": "unexpected_schema", "key_presence": "unverified"}
    return {"container": "observed", "key_presence": state}


def check_sdk_version() -> str:
    """Fingerprint only the LiteLLM package version; never inspect credentials."""
    command = ["docker", "exec", "litellm", "python3", "-c",
               "from importlib.metadata import version; print(version('litellm'))"]
    try:
        result = subprocess.run(command, capture_output=True,
                                check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return "unverified"
    if result.returncode != 0 or result.stderr or len(result.stdout) > 64:
        return "unverified"
    value = result.stdout.decode("ascii", errors="replace").strip()
    # Strict version fingerprint; never echo arbitrary process output.
    import re
    return value if re.fullmatch(r"[0-9]+(?:\\.[0-9]+){1,3}(?:[-+][a-zA-Z0-9.]+)?",
                                value) else "unverified"


def check_liveliness() -> str:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(PROXY + "/health/liveliness")
    try:
        with opener.open(request, timeout=4) as res:
            return "http_200" if res.status == 200 else "unexpected_http"
    except HTTPError as e:
        return "auth_required" if e.code in (401, 403) else "unexpected_http"
    except (OSError, URLError, TimeoutError):
        return "unavailable"


def classify_upstream_keys(container: dict) -> str:
    """Presence is a necessary prerequisite, never a successful auth proof."""
    if container.get("container") != "observed":
        return "unverified"
    states = container.get("key_presence")
    if not isinstance(states, dict) or set(states) != set(KEYS):
        return "unverified"
    if any(states.get(key) not in {"present", "absent"} for key in KEYS):
        return "unverified"
    return "all_present_unvalidated" if all(
        states[key] == "present" for key in KEYS
    ) else "missing_runtime_upstream_key"


def report() -> dict:
    container = check_container()
    return {
        "schema": "nabla-litellm-upstream-auth-preflight/v2",
        "proxy_target": "workstation_litellm",
        "truenas_litellm_env": container,
        "truenas_upstream_key_state": classify_upstream_keys(container),
        "workstation_liveliness": check_liveliness(),
        "origin_of_previous_missing_key_event": "not_yet_attributed",
        "suspected_component": "truenas_litellm_or_other_sdk_unverified",
        "truenas_litellm_sdk_version": check_sdk_version(),
        "reported_failure_user_agent_version": "1.106.4",
        "protected_models_endpoint_queried": False,
        "model_requests_sent": 0,
        "secret_values_printed": False,
        "runtime_mutated": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", required=True)
    p.parse_args(argv)
    record = report()
    print(json.dumps(record, sort_keys=True))
    # Never return green when any declared upstream key is missing.
    # All-present means presence only, not that the key is valid or in scope.
    return 0 if (record["truenas_upstream_key_state"] == "all_present_unvalidated"
                 and record["workstation_liveliness"] == "http_200") else 2


if __name__ == "__main__":
    raise SystemExit(main())
