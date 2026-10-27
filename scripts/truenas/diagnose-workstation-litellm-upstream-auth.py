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


def report() -> dict:
    return {
        "schema": "nabla-litellm-upstream-auth-preflight/v1",
        "proxy_target": "workstation_litellm",
        "truenas_litellm_env": check_container(),
        "workstation_liveliness": check_liveliness(),
        "origin_of_previous_missing_key_event": "not_yet_attributed",
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
    return 0 if (record["truenas_litellm_env"]["container"] == "observed"
                 and record["workstation_liveliness"] == "http_200") else 2


if __name__ == "__main__":
    raise SystemExit(main())
