#!/usr/bin/env python3
"""Read-only TrueNAS LiteLLM -> Workstation LiteLLM auth preflight.

Does NOT send protected model requests, call models or read credential values.
Resolves the unique running TrueNAS Compose LiteLLM service by strict name.
Never targets stopped legacy containers or reads secret values.
"""
from __future__ import annotations

import argparse
import json
import re
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


def failure_class(returncode: int, stderr: bytes) -> str:
    """Classify Docker failures with fixed labels; never expose raw stderr."""
    if len(stderr) > 16384:
        return "stderr_oversized"
    message = stderr.decode("utf-8", errors="replace").lower()
    if "permission denied" in message or "access is denied" in message:
        return "docker_permission_denied"
    if "cannot connect to the docker daemon" in message or "daemon is not running" in message:
        return "docker_daemon_unavailable"
    if "no such container" in message or "no such object" in message:
        return "container_not_found"
    if "container" in message and "not running" in message:
        return "container_not_running"
    if ("executable file not found" in message or 'exec: "python3"' in message
            or "python3: not found" in message):
        return "python3_missing_in_container"
    if "syntaxerror" in message or "traceback (most recent call last)" in message:
        return "probe_python_failed"
    return "unexpected_stderr" if returncode == 0 else "docker_exec_failed"


# TrueNAS can use a generated Compose project name rather than the
# literal "litellm". Therefore project=litellm is NOT a reliable filter.
# Accept only the canonical service container name observed by the operator.
# Never select the stopped/legacy bare "litellm" container.
CONTAINER_ROW = re.compile(r"([0-9a-f]{12,64})\|(litellm-litellm-[1-9][0-9]*)")
DOCKER_PS_ROW = re.compile(r"[0-9a-f]{12,64}\|[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def discover_running_container() -> tuple[str, str | None, str | None]:
    """Return (state, Docker ID, exact name) without printing Docker IDs.

    Select one running, exact-name TrueNAS Compose service container. The
    narrow name filter is for discovery only; regex enforces the full name.
    Reject ambiguity and do not fall back to the bare legacy container.
    """
    command = ["docker", "ps", "--filter", "name=litellm",
               "--filter", "status=running", "--format",
               "{{.ID}}|{{.Names}}"]
    try:
        result = subprocess.run(command, capture_output=True,
                                check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return "docker_discovery_unavailable", None, None
    if result.returncode:
        return failure_class(result.returncode, result.stderr), None, None
    if result.stderr or len(result.stdout) > 4096:
        return "docker_discovery_unverified", None, None
    lines = result.stdout.decode("ascii", errors="replace").splitlines()
    candidates = []
    for line in lines:
        if DOCKER_PS_ROW.fullmatch(line) is None:
            return "docker_discovery_unverified", None, None
        match = CONTAINER_ROW.fullmatch(line)
        if match is not None:
            candidates.append((match.group(1), match.group(2)))
    if not candidates:
        return "compose_running_container_not_found", None, None
    if len(candidates) != 1:
        return "compose_running_container_ambiguous", None, None
    return "selected", candidates[0][0], candidates[0][1]


def inspect_docker_target(container_id: str = "litellm") -> str:
    """Only inspect container running state, not Docker Env or secret mounts."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--type", "container", "--format",
             "{{.State.Status}}", container_id],
            capture_output=True, check=False, timeout=8
        )
    except (OSError, subprocess.TimeoutExpired):
        return "docker_inspect_unavailable"
    if result.returncode != 0:
        return failure_class(result.returncode, result.stderr)
    if result.stderr or len(result.stdout) > 64:
        return "docker_inspect_unverified"
    status = result.stdout.decode("ascii", errors="replace").strip()
    if status in ("running", "exited", "restarting", "created", "paused", "dead", "removing"):
        return status
    return "docker_inspect_unverified"


def check_container(container_id: str = "litellm") -> dict:
    try:
        cp = subprocess.run(
            ["docker", "exec", container_id, "python3", "-c", PRESENCE_SCRIPT],
            capture_output=True, check=False, timeout=8
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"container": "unavailable", "key_presence": "unverified"}
    if cp.returncode != 0 or cp.stderr:
        return {"container": "unavailable", "key_presence": "unverified",
                "failure_class": failure_class(cp.returncode, cp.stderr)}
    if len(cp.stdout) > 512:
        return {"container": "unexpected_schema", "key_presence": "unverified",
                "failure_class": "stdout_oversized"}
    lines = cp.stdout.decode("ascii", errors="replace").splitlines()
    expected = {name + "=present" for name in KEYS} | {name + "=absent" for name in KEYS}
    if len(lines) != len(KEYS) or any(line not in expected for line in lines):
        return {"container": "unexpected_schema", "key_presence": "unverified"}
    state = {line.split("=")[0]: line.split("=")[1] for line in lines}
    if set(state) != set(KEYS):
        return {"container": "unexpected_schema", "key_presence": "unverified"}
    return {"container": "observed", "key_presence": state}


def check_sdk_version(container_id: str = "litellm") -> str:
    """Fingerprint only the LiteLLM package version; never inspect credentials."""
    command = ["docker", "exec", container_id, "python3", "-c",
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
    return value if re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+][a-zA-Z0-9.]+)?",
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
    selection, container_id, selected_name = discover_running_container()
    docker_status = (inspect_docker_target(container_id) if container_id is not None
                     else "not_inspected")
    should_inspect = selection == "selected" and docker_status == "running"
    container = (check_container(container_id) if should_inspect
                 else {"container": "unavailable", "key_presence": "unverified",
                       "failure_class": "container_selection_or_state_unverified"})
    sdk = check_sdk_version(container_id) if should_inspect else "unverified"
    return {
        "schema": "nabla-litellm-upstream-auth-preflight/v3",
        "proxy_target": "workstation_litellm",
        "truenas_container_selection": selection,
        "truenas_selection_method": "unique_running_exact_name",
        "truenas_docker_container_name": selected_name if should_inspect else "unverified",
        "truenas_docker_container_status": docker_status,
        "truenas_litellm_env": container,
        "truenas_upstream_key_state": classify_upstream_keys(container),
        "workstation_liveliness": check_liveliness(),
        "origin_of_previous_missing_key_event": "not_yet_attributed",
        "suspected_component": "truenas_litellm_or_other_sdk_unverified",
        "truenas_litellm_sdk_version": sdk,
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
    return 0 if (record["truenas_container_selection"] == "selected"
                 and record["truenas_docker_container_status"] == "running"
                 and record["truenas_upstream_key_state"] == "all_present_unvalidated"
                 and record["workstation_liveliness"] == "http_200") else 2


if __name__ == "__main__":
    raise SystemExit(main())
