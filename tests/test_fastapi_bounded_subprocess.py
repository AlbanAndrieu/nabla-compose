"""Bounded subprocess capture contracts; never query TrueNAS or secrets."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-fastapi-stack.py"
SPEC = importlib.util.spec_from_file_location("bounded_fastapi_stack", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
stack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stack)


def test_small_json_and_nonzero_child_keep_the_existing_contract() -> None:
    command = [sys.executable, "-c", "import json,sys; print(json.dumps({'status': 'ok'})); sys.exit(2)"]
    state, report, raw = stack.run(command, timeout=3)
    assert state == "nonzero"
    assert report == {"status": "ok"}
    assert '"status"' in raw


def test_oversized_child_is_rejected_without_returning_sensitive_output() -> None:
    command = [
        sys.executable, "-c",
        f'import os; os.write(1, b"PRIVATE_TOKEN_" * {stack.MAX_JSON_BYTES})',
    ]
    state, report, raw = stack.run(command, timeout=4)
    assert state == "invalid"
    assert report == {}
    assert raw == ""


def test_timeout_terminates_child_without_returning_output() -> None:
    command = [
        sys.executable, "-c",
        'import time; print("PRIVATE", flush=True); time.sleep(10)',
    ]
    start = time.monotonic()
    state, report, raw = stack.run(command, timeout=0.3)
    assert state == "timeout"
    assert report == {}
    assert raw == ""
    assert time.monotonic() - start < 4


def test_descendant_inheriting_stdout_cannot_hold_probe_indefinitely() -> None:
    if os.name != "posix":
        pytest.skip("process group supervision is POSIX-only")
    command = [
        sys.executable, "-c",
        ('import subprocess, sys; '
         'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"]); '
         'print("{}")'),
    ]
    start = time.monotonic()
    state, report, raw = stack.run(command, timeout=0.4)
    assert (state, report, raw) == ("timeout", {}, "")
    assert time.monotonic() - start < 4


def test_missing_executable_is_not_run() -> None:
    state, report, raw = stack.run(
        ["/no-such-program-for-bounded-fastapi-tests"], timeout=1,
    )
    assert (state, report, raw) == ("missing", {}, "")


def test_child_stderr_is_never_returned() -> None:
    command = [
        sys.executable, "-c",
        'import sys; sys.stderr.write("PRIVATE_STDERR"); print("{}")',
    ]
    state, report, raw = stack.run(command, timeout=3)
    assert state == "ok"
    assert report == {}
    assert "PRIVATE_STDERR" not in raw


def test_subprocess_source_uses_streaming_cap_and_group_cleanup() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    helper = (ROOT / "scripts/lib/bounded_subprocess.py").read_text(encoding="utf-8")
    assert "capture_bounded(argv, cwd=ROOT, timeout=timeout, limit=MAX_JSON_BYTES)" in source
    assert "selectors.DefaultSelector()" in helper
    assert "limit + 1 - len(output)" in helper
    assert "start_new_session=True" in helper
    assert "os.killpg(process.pid, signal.SIGKILL)" in helper
    assert "stdout=subprocess.PIPE" in helper
    assert "subprocess.run(argv" not in source
