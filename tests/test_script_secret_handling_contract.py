"""Regression contracts for secret handling in operator shell scripts.

Secrets passed as command-line arguments are readable by any local user
through ps(1) and /proc/<pid>/cmdline, and container processes are visible
from the host. These tests keep secret values out of argv and keep the
quality gate from silently disabling secret scanners.
"""

from __future__ import annotations

import http.server
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECRETS_LIB = ROOT / "scripts" / "lib" / "secrets.sh"

SECRET_HEADER_IN_ARGV = re.compile(
    r"""(?:-H|--header)[ =]+["']?"""
    r"""(?:Authorization|X-Api-Key|X-API-Key|X-Diagnostics-Key|CF-Access-Client-(?:Id|Secret))"""
    r"""\s*:[^"'\n]*\$""",
)
SECRET_ENV_IN_ARGV = re.compile(
    r"""(?:\s-e|--env)\s+[A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET)[A-Z0-9_]*=["']?\$"""
)


def tracked_shell_sources() -> list[Path]:
    files = subprocess.run(
        ["git", "ls-files", "--", "*.sh", ".envrc", "Makefile"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    # Submodule checkouts are owned by their upstream repositories.
    return [ROOT / name for name in files if (ROOT / name).is_file()]


def run_bash(script: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def test_no_script_puts_a_secret_header_or_env_value_in_argv() -> None:
    offenders = []
    for path in tracked_shell_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if SECRET_HEADER_IN_ARGV.search(line) or SECRET_ENV_IN_ARGV.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == [], (
        "pass secrets with `--header @<(secrets_curl_headers ...)` or "
        "`NAME=value docker exec -e NAME`, not in argv: " + ", ".join(offenders)
    )


def test_secrets_curl_headers_validates_before_printing() -> None:
    lib = SECRETS_LIB.as_posix()
    ok = run_bash(f'source "{lib}"; secrets_curl_headers Authorization "Bearer t0k" X-A b')
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout == "Authorization: Bearer t0k\nX-A: b\n"

    for args, code in (
        ("X-A ok X-B ''", 1),
        ("X-A $'a\\nb'", 1),
        ("X-A $'a\\rb'", 1),
        ("X-A", 2),
        ("'Bad Name' v", 2),
    ):
        rejected = run_bash(f'source "{lib}"; secrets_curl_headers {args}')
        assert rejected.returncode == code, (args, rejected.stderr)
        # A rejected call must not emit a partial header set.
        assert rejected.stdout == "", args


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is required")
def test_secret_header_reaches_server_without_appearing_in_argv() -> None:
    received: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            received.update(self.headers.items())
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        result = run_bash(
            f'source "{SECRETS_LIB.as_posix()}"\n'
            f'curl -fsS --header @<(secrets_curl_headers Authorization "Token s3cr3t") "{url}"'
        )
        # printf receives exactly the argv curl receives above.
        argv = run_bash(
            f'source "{SECRETS_LIB.as_posix()}"\n'
            'printf "%s\\n" --header @<(secrets_curl_headers Authorization "Token s3cr3t")'
        ).stdout
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stderr
    assert received.get("Authorization") == "Token s3cr3t"
    assert "s3cr3t" not in argv
    assert re.search(r"^@/dev/fd/\d+$", argv, re.MULTILINE), argv


def test_kill_container_matches_exact_names_only(tmp_path: Path) -> None:
    calls = tmp_path / "calls.log"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >>"{calls}"\n'
        'if [[ "$1" == ps && "$*" == *--no-trunc* ]]; then\n'
        '  printf "%s\\n" "aaaa temporal-frontend-1" "bbbb temporal-frontend"\n'
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "NO_COLOR": "1"}

    exact = subprocess.run(
        ["bash", "kill-container.sh", "temporal-frontend"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert exact.returncode == 0, exact.stderr
    assert "stop bbbb" in calls.read_text(encoding="utf-8")
    assert "aaaa" not in calls.read_text(encoding="utf-8").replace("ps --no-trunc", "")

    calls.write_text("", encoding="utf-8")
    substring = subprocess.run(
        ["bash", "kill-container.sh", "temporal"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert substring.returncode == 1
    assert "not found in running containers" in substring.stderr
    assert "stop" not in calls.read_text(encoding="utf-8")


@pytest.mark.parametrize("skip", ["betterleaks", "service-topology-sync, betterleaks", "detect-private-key"])
def test_quality_gate_refuses_skip_of_secret_scanners(skip: str) -> None:
    result = subprocess.run(
        ["bash", "scripts/agent-quality-gate.sh", "--preflight"],
        cwd=ROOT,
        env={**os.environ, "SKIP": skip},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 2
    assert "SKIP must not disable the" in result.stderr


def test_smoke_cleanup_only_deletes_owned_namespaces() -> None:
    script = (ROOT / "scripts" / "talos" / "smoke-fastapi-sample.sh").read_text(encoding="utf-8")
    cleanup = script[script.index('if [[ "${MODE}" == "--cleanup" ]]; then'):]
    cleanup = cleanup[: cleanup.index("\nfi\n")]
    assert "app.kubernetes.io/managed-by" in cleanup
    assert "refusing to delete namespace" in cleanup
    assert cleanup.index("refusing to delete namespace") < cleanup.index("kubectl delete namespace")
    assert "app.kubernetes.io/managed-by: ${SMOKE_MANAGED_BY}" in script


def test_envrc_and_helpers_do_not_pipe_remote_installers_or_leak() -> None:
    envrc = (ROOT / ".envrc").read_text(encoding="utf-8")
    code = "\n".join(line for line in envrc.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"curl[^\n|]*\|\s*(?:ba)?sh\b", code)
    assert not re.search(r"^\s*pip install ", code, re.MULTILINE)

    litellm = (ROOT / "build-litellm.sh").read_text(encoding="utf-8")
    assert "set -x" not in litellm
    assert "${DATABASE_URL}" not in litellm

    sentry = (ROOT / "scripts" / "truenas" / "smoke-sentry-event.sh").read_text(encoding="utf-8")
    assert "/tmp/nabla-sentry-smoke-response.txt" not in sentry


def test_secrets_curl_headers_never_echoes_a_value_in_errors() -> None:
    rejected = run_bash(f'source "{SECRETS_LIB.as_posix()}"; secrets_curl_headers X-A $\'s3cr3t\\n\'')
    assert rejected.returncode == 1
    assert "s3cr3t" not in rejected.stderr
