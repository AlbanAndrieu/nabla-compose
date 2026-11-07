"""Bounded stdout capture for explicit, local, read-only diagnostics.

Never collect stderr or expose command output through exceptions. Only the
caller can interpret the bytes as JSON or static diagnostic status codes.
POSIX process groups ensure a timeout cannot leave stdout inherited by a child.
"""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from pathlib import Path


def capture_bounded(
    argv: list[str], *, cwd: Path, timeout: float, limit: int,
) -> tuple[int, bytes] | None:
    """Return (exit status, bounded stdout), or None on excessive output.

    A single monotonic deadline bounds pipe reading and process termination.
    No intermediate raw output file is created on TrueNAS.
    """
    if type(limit) is not int or limit < 1 or timeout <= 0:
        raise ValueError("invalid capture bounds")
    process = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    output = bytearray()
    finished = False
    deadline = time.monotonic() + timeout
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired(argv, timeout)
                block = os.read(
                    process.stdout.fileno(),
                    min(8192, limit + 1 - len(output)),
                )
                if not block:
                    selector.unregister(process.stdout)
                    break
                output.extend(block)
                if len(output) > limit:
                    return None
        returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        finished = True
        return returncode, bytes(output)
    finally:
        if not finished:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.poll() is None:
                process.kill()
        process.wait()
        if process.stdout is not None:
            process.stdout.close()
