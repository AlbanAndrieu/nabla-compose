#!/usr/bin/env python3
"""Bounded, explicit agent diagnostics: offline by default; no implicit runtime.

A plan is not a PASS. Execute only fixed, source-controlled commands; never
send credentials to tests, print logs, install packages or run remote CI.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

# Commands are fixed argv arrays; no shell expansion, no user arguments.
OFFLINE = {
    "policy": (
        ("precedence", (PYTHON, "scripts/quality/check-agent-skill-precedence.py")),
        ("precedence-tests", (PYTHON, "-m", "unittest", "discover", "-s",
                              "tests", "-p", "test_agent_skill_precedence_contract.py", "-q")),
    ),
    "compose": (
        ("compose-config", ("docker", "compose", "config", "--quiet",
                            "--no-interpolate", "--no-env-resolution")),
    ),
    "openclaw": (
        ("openclaw-tests", (PYTHON, "-m", "unittest", "discover", "-s",
                            "tests", "-p", "test_openclaw_migration_evidence.py", "-q")),
    ),
    "secrets": (
        ("secret-source-tests", (PYTHON, "-m", "unittest", "discover", "-s",
                                 "tests", "-p", "test_litellm_fastapi_upstream_source.py", "-q")),
    ),
}
# Existing host probes, never attempted unless explicitly selected on Workstation.
RUNTIME_READONLY = {
    "openclaw": ("openclaw-readonly", ("just", "openclaw-migration-evidence-check")),
}

# Whitelist only non-credential execution environment for offline contracts.
OFFLINE_ENV = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL",
    "VIRTUAL_ENV", "TMPDIR", "XDG_CACHE_HOME", "MISE_DATA_DIR",
)

REQUIRED_TEST = {
    "precedence-tests": "test_agent_skill_precedence_contract.py",
    "openclaw-tests": "test_openclaw_migration_evidence.py",
    "secret-source-tests": "test_litellm_fastapi_upstream_source.py",
}


def planned(scope: str, mode: str, runtime: bool) -> list[dict]:
    steps = [{"id": name, "argv": list(argv), "type": "offline", "status": "NOT_RUN"}
             for name, argv in OFFLINE[scope]]
    if runtime:
        if mode != "workstation" or scope not in RUNTIME_READONLY:
            raise ValueError("runtime checks require workstation mode and a supported scope")
        name, argv = RUNTIME_READONLY[scope]
        steps.append({"id": name, "argv": list(argv), "type": "runtime_readonly",
                      "status": "NOT_RUN"})
    return steps


def safe_environment(runtime: bool = False) -> dict[str, str]:
    env = os.environ.copy() if runtime else {
        key: os.environ[key] for key in OFFLINE_ENV if key in os.environ
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    return env


def workstation_runtime_ready() -> bool:
    """Require local user systemd Gateway unit before any OpenClaw host probe."""
    if sys.platform != "linux" or os.getenv("CI"):
        return False
    try:
        status = subprocess.run(
            ["systemctl", "--user", "show", "openclaw-gateway.service",
             "-p", "LoadState", "--value"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=4, check=False, env=safe_environment(runtime=True),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return status.returncode == 0 and status.stdout.strip() == b"loaded"


def run_steps(steps: list[dict], root: Path, timeout: int) -> bool:
    """Run at most one bounded command at a time. Never capture/show output."""
    ok = True
    for index, step in enumerate(steps):
        argv = step["argv"]
        required = REQUIRED_TEST.get(step["id"])
        if required and not (root / "tests" / required).is_file():
            step["status"] = "MISSING_TEST"
        elif shutil.which(argv[0]) is None and not Path(argv[0]).is_file():
            step["status"] = "TOOL_MISSING"
        else:
            step["status"] = "RUNNING"
        if step["status"] != "RUNNING":
            for pending in steps[index + 1:]:
                pending["status"] = "NOT_RUN_AFTER_FAILURE"
            return False
        started = time.monotonic()
        try:
            # No shell; discard output to keep tokens, secrets and memory bounded.
            result = subprocess.run(
                argv, cwd=root, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout,
                env=safe_environment(step["type"] == "runtime_readonly"),
                check=False,
            )
            step["status"] = ("PASS" if result.returncode == 0 else
                              "UNVERIFIED" if step["type"] == "runtime_readonly"
                              else "FAILED")
            step["exit_code"] = result.returncode
            if result.returncode:
                ok = False
        except subprocess.TimeoutExpired:
            step["status"] = "TIMEOUT"
            ok = False
        except OSError:
            step["status"] = "TOOL_UNAVAILABLE"
            ok = False
        step["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        # Don't run later probes after the first failure: avoid expensive noise.
        if not ok:
            for pending in steps[index + 1:]:
                pending["status"] = "NOT_RUN_AFTER_FAILURE"
            break
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("remote", "workstation"),
                        default="remote")
    parser.add_argument("--scope", choices=tuple(OFFLINE), default="policy")
    parser.add_argument("--execute", action="store_true",
                        help="run only the selected fixed diagnostic commands")
    parser.add_argument("--runtime-readonly", action="store_true",
                        help="explicit Workstation-only runtime probe, never by default")
    parser.add_argument("--timeout", type=int, default=45,
                        help="per-step timeout in seconds, 1..180")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if not 1 <= args.timeout <= 180:
        parser.error("--timeout must be between 1 and 180")
    root = args.root.resolve()
    status = "PLAN_ONLY"
    try:
        steps = planned(args.scope, args.mode, args.runtime_readonly)
    except ValueError:
        status = "BLOCKED_MODE"
        steps = []
    if args.execute and not steps:
        status = "BLOCKED_MODE"
    elif args.execute:
        # Offline source tests can run in a remote checkout. Runtime cannot.
        if not (root / "AGENTS.md").is_file():
            status = "NO_CHECKOUT"
        elif args.runtime_readonly and not workstation_runtime_ready():
            status = "HOST_UNVERIFIED"
        else:
            status = "PASS" if run_steps(steps, root, args.timeout) else "UNVERIFIED"
    print(json.dumps({
        "schema": "nabla-agent-diagnostics/v1",
        "mode": args.mode, "scope": args.scope, "status": status,
        "executed": bool(args.execute and status not in ("BLOCKED_MODE", "NO_CHECKOUT", "HOST_UNVERIFIED")),
        "runtime_allowed": bool(args.mode == "workstation" and args.runtime_readonly),
        "steps": steps,
    }, sort_keys=True, separators=(",", ":")))
    return 2 if status in ("BLOCKED_MODE", "NO_CHECKOUT", "HOST_UNVERIFIED", "UNVERIFIED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
