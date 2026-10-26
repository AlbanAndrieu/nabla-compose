#!/usr/bin/env python3
"""Offline AI wiring audit; optional read-only HTTP transport checks from FastAPI.

Never read secret values, prompt texts, Bababou files or OpenRAG search results.
Does not mutate running services. A reachable endpoint is NOT an authorized RAG.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "sample": ROOT / "apps/sample/compose.yml",
    "litellm": ROOT / "apps/litellm/config.yaml",
    "ollama": ROOT / "apps/ollama/compose.yml",
    "openrag": ROOT / "apps/openrag/compose.yml",
}
SERVICES = frozenset(("litellm", "ollama", "openrag_backend", "openrag_search", "openrag_mcp"))
HTTP_CODES = frozenset(("http_200", "http_400", "http_401", "http_403", "http_404", "http_405", "unverified", "not_tested_requires_auth"))
SSH_TARGET = re.compile(r"[a-z_][a-z0-9_-]{0,31}@172[.]17[.]0[.]24\Z")
MAX_RUNTIME_REPORT = 4096
READ_ONLY_PROBE = r'''
import json, urllib.request, urllib.error
urls = {
 "litellm": "http://172.17.0.24:4000/health/liveliness",
 "ollama": "http://172.17.0.24:30068/api/tags",
 "openrag_backend": "http://openrag-backend:8000/health",
 "openrag_mcp": "http://openrag-frontend:3000/mcp",
}
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
out = {}
for service, url in urls.items():
    try:
        with client.open(urllib.request.Request(url, method="GET"), timeout=3) as reply:
            status = reply.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except (OSError, ValueError, TimeoutError):
        status = None
    out[service] = "http_" + str(status) if status in (200, 400, 401, 403, 404, 405) else "unverified"
out["openrag_search"] = "not_tested_requires_auth"
print(json.dumps(out, sort_keys=True))
'''


def _read(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def inspect_declared(sources: dict[str, str | None]) -> dict[str, str]:
    """Check versioned connectivity contracts, not runtime or private data."""
    sample, litellm, ollama, openrag = (sources.get(k) or "" for k in SOURCES)
    if not all((sample, litellm, ollama, openrag)):
        return {name: "source_unavailable" for name in (
            "fastapi_litellm", "litellm_upstream", "ollama_truenas",
            "openrag_bababou_mount", "fastapi_openrag_mcp",
        )}
    bridge = (
        "LITELLM_URL: http://172.17.0.24:4000" in sample
        and "DEFAULT_CHAT_MODEL: fastapi-qwen" in sample
        and "/mnt/cpool/secrets/runtime/sample/.env.secrets" in sample
        and "      intranet: {}" in sample
    )
    upstream = (
        re.search(r"(?m)^  - model_name: fastapi-qwen\s*$", litellm) is not None
        and "LITELLM_FASTAPI_WORKSTATION_API_KEY" in litellm
        and "LITELLM_WORKSTATION_API_BASE" in litellm
    )
    local = "OLLAMA_HOST=0.0.0.0:30068" in ollama and "30068:30068" in ollama
    mount = (
        "OPENRAG_BABABOU_SOURCE" in openrag
        and "target: /mnt/bababou" in openrag
        and "read_only: true" in openrag
        and "create_host_path: false" in openrag
        and "      - intranet" in openrag
    )
    return {
        "fastapi_litellm": "declared" if bridge else "configuration_drift",
        "litellm_upstream": "declared" if upstream else "configuration_drift",
        "ollama_truenas": "declared_unverified" if local else "configuration_drift",
        "openrag_bababou_mount": "declared_unverified" if mount else "configuration_drift",
        "fastapi_openrag_mcp": "not_wired_pending_private_acl",
    }


def inspect_runtime() -> dict[str, str]:
    """Never print Docker errors, response bodies or HTTP authentication data."""
    try:
        run = subprocess.run(
            ["docker", "exec", "fastapi-sample", "python3", "-c", READ_ONLY_PROBE],
            capture_output=True, text=True, timeout=28, check=False,
        )
        if run.returncode or len(run.stdout) > 4096:
            return {"runtime": "docker_unavailable_or_probe_failed"}
        data = json.loads(run.stdout)
        if not isinstance(data, dict) or set(data) != SERVICES:
            return {"runtime": "runtime_report_invalid"}
        if any(value not in HTTP_CODES for value in data.values()):
            return {"runtime": "runtime_report_invalid"}
        return {key: data[key] for key in sorted(SERVICES)}
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return {"runtime": "docker_unavailable_or_probe_failed"}


def build_remote_probe(docker: list[str]) -> str:
    """Build the fixed remote probe. No inputs from SSH output or private env."""
    prefix = (
        "import json,subprocess,shutil\n"
        "code = " + repr(READ_ONLY_PROBE) + "\n"
        "docker = " + repr(docker) + "\n"
        "command = docker + ['exec', 'fastapi-sample', 'python3', '-c', code]\n"
        "expected = " + repr(set(SERVICES)) + "\n"
        "allowed = " + repr(set(HTTP_CODES)) + "\n"
    )
    return prefix + '''
def fixed(state):
    print(json.dumps({"runtime": state}, sort_keys=True))

def classify(stderr):
    diagnostic = stderr.lower()[:4096]
    if "a password is required" in diagnostic or "sudo: a terminal is required" in diagnostic:
        return "sudo_noninteractive_denied"
    if "permission denied" in diagnostic and ("docker.sock" in diagnostic or "docker daemon socket" in diagnostic):
        return "docker_socket_denied"
    if "cannot connect to the docker daemon" in diagnostic or "is the docker daemon running" in diagnostic:
        return "docker_daemon_unavailable"
    if "no such container" in diagnostic:
        return "fastapi_container_missing"
    if "is not running" in diagnostic or "container is paused" in diagnostic:
        return "fastapi_container_not_running"
    if "executable file not found" in diagnostic and "python3" in diagnostic:
        return "fastapi_container_python_missing"
    return "docker_exec_failed"

try:
    if shutil.which(docker[0]) is None:
        fixed("sudo_binary_missing" if docker[0] == "sudo" else "docker_cli_missing")
    else:
        result = subprocess.run(command, capture_output=True, text=True, timeout=22)
        if result.returncode != 0:
            fixed(classify(result.stderr))
        elif len(result.stdout) > 4096:
            fixed("probe_output_invalid")
        else:
            try:
                report = json.loads(result.stdout)
                if not isinstance(report, dict) or set(report) != expected:
                    fixed("probe_output_invalid")
                elif any(value not in allowed for value in report.values()):
                    fixed("probe_output_invalid")
                else:
                    print(json.dumps(report, sort_keys=True))
            except (ValueError, TypeError):
                fixed("probe_output_invalid")
except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
    fixed("docker_exec_failed")
'''


REMOTE_FAILURE_STATES = frozenset({
    "sudo_noninteractive_denied",
    "docker_socket_denied",
    "docker_daemon_unavailable",
    "fastapi_container_missing",
    "fastapi_container_not_running",
    "fastapi_container_python_missing",
    "docker_exec_failed",
    "docker_cli_missing",
    "sudo_binary_missing",
    "probe_output_invalid",
})

RUNTIME_NEXT_CHECK = {
    "ssh_target_invalid": "verify_ssh_account_host_and_port",
    "ssh_unavailable_or_unauthorized": "verify_ssh_transport_with_batchmode",
    "remote_report_invalid": "verify_remote_python3_and_shell_startup_output",
    "docker_cli_missing": "verify_docker_cli_in_remote_ssh_path",
    "sudo_binary_missing": "verify_noninteractive_sudo_binary_on_truenas",
    "sudo_noninteractive_denied": "verify_existing_sudo_noninteractive_authorization",
    "docker_socket_denied": "use_ssh_sudo_only_if_already_authorized",
    "docker_daemon_unavailable": "verify_truenas_docker_service_readonly",
    "fastapi_container_missing": "verify_fastapi_container_name_in_docker_ps",
    "fastapi_container_not_running": "inspect_fastapi_container_state_readonly",
    "fastapi_container_python_missing": "verify_fastapi_container_python_runtime",
    "docker_exec_failed": "inspect_sanitized_container_diagnostics_locally",
    "probe_output_invalid": "verify_python_probe_execution_in_fastapi_container",
    "docker_unavailable_or_probe_failed": "verify_local_docker_permissions_and_container_state",
    "runtime_report_invalid": "verify_local_probe_output_contract",
}


def inspect_ssh_runtime(target: str, *, port: int | None = None,
                        sudo: bool = False) -> dict[str, str]:
    """Classify SSH/Docker failure without ever exposing the remote stderr."""
    if not SSH_TARGET.fullmatch(target) or (
        port is not None and not 1 <= port <= 65535
    ):
        return {"runtime": "ssh_target_invalid"}
    docker = ["sudo", "-n", "docker"] if sudo else ["docker"]
    command = [
        "ssh", "-T", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=7",
    ]
    if port is not None:
        command.extend(("-p", str(port)))
    command.extend((target, "python3 -"))
    try:
        response = subprocess.run(
            command, input=build_remote_probe(docker), capture_output=True,
            text=True, timeout=35, check=False,
        )
        if response.returncode != 0 or len(response.stdout) > MAX_RUNTIME_REPORT:
            return {"runtime": "ssh_unavailable_or_unauthorized"}
        result = json.loads(response.stdout)
        if not isinstance(result, dict):
            return {"runtime": "remote_report_invalid"}
        if set(result) == {"runtime"} and result["runtime"] in REMOTE_FAILURE_STATES:
            return result
        if set(result) != SERVICES or any(value not in HTTP_CODES for value in result.values()):
            return {"runtime": "remote_report_invalid"}
        return {key: result[key] for key in sorted(SERVICES)}
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return {"runtime": "ssh_unavailable_or_unauthorized"}



def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", required=True)
    p.add_argument("--runtime", action="store_true",
                   help="Explicit, anonymous read-only transport probes on TrueNAS")
    p.add_argument("--ssh-target", help="Optional pinned account@172.17.0.24; uses ~/.ssh/config")
    p.add_argument("--ssh-port", type=int, default=None, help="Only for an explicit SSH port override")
    p.add_argument("--ssh-sudo", action="store_true", help="Use pre-authorized sudo -n for remote Docker")
    args = p.parse_args(argv)
    if args.ssh_target and not args.runtime:
        p.error("--ssh-target requires --runtime")
    if args.ssh_port is not None and not args.ssh_target:
        p.error("--ssh-port requires --ssh-target")
    if args.ssh_sudo and not args.ssh_target:
        p.error("--ssh-sudo requires --ssh-target")
    declarations = inspect_declared({name: _read(path) for name, path in SOURCES.items()})
    report = {
        "component": "fastapi_truenas_ai_rag",
        "declared": declarations,
        "runtime": (
            inspect_ssh_runtime(args.ssh_target, port=args.ssh_port, sudo=args.ssh_sudo)
            if args.runtime and args.ssh_target
            else inspect_runtime() if args.runtime
            else {"runtime": "not_run"}
        ),
        "bababou_private_retrieval": "not_verified",
        "next_check": "validate_scoped_litellm_key_openrag_readonly_acl_and_private_index",
    }
    if set(report["runtime"]) == {"runtime"}:
        state = report["runtime"]["runtime"]
        if state in RUNTIME_NEXT_CHECK:
            report["runtime_next_check"] = RUNTIME_NEXT_CHECK[state]
    print(json.dumps(report, sort_keys=True))
    return 1 if "configuration_drift" in declarations.values() else 2


if __name__ == "__main__":
    raise SystemExit(main())
