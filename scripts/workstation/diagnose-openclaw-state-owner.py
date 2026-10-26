#!/usr/bin/env python3
"""Read-only OpenClaw Gateway SQLite owner census after EXIT_CONFIG 78.

A historical contention error is evidence, not proof of a CURRENT owner.
Never touch SQLite, remove journal files, kill PIDs, run Doctor or restart.
Return fixed classifications without copying CLI arguments, logs or secrets.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess

MAX_PID = 4194304
UNIT = "openclaw-gateway.service"


def previous_diagnostics():
    path = Path(__file__).with_name("diagnose-openclaw-gateway-service-failure.py")
    spec = importlib.util.spec_from_file_location("openclaw_service_failure", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("diagnostic_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def holder_from_lines(lines):
    """Read the last contention *record* in a bounded local log sample."""
    if not lines:
        return None
    start = -1
    for i, line in enumerate(lines):
        if re.search(r"GatewayStateOwnerContentionError|state database is busy",
                     line, flags=re.IGNORECASE):
            start = i
    if start < 0:
        return None
    # The holder and PID may be on a following line. Do not capture
    # unrelated PIDs from earlier warnings or arbitrary log entries.
    portion = "\n".join(lines[start:start + 6])
    match = re.search(r"\bholder\s+([1-9]\d{0,6})\b", portion)
    if match is None:
        return None
    pid = int(match.group(1))
    return pid if 0 < pid <= MAX_PID else None


def safe_sqlite_files():
    state_dir = Path(os.environ.get(
        "OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw")))
    database = state_dir / "state" / "openclaw.sqlite"
    entries = [database, Path(str(database) + "-wal"), Path(str(database) + "-shm")]
    files = []
    for path in entries:
        try:
            st = path.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return None
        # Only inspect the user-owned regular files without following links.
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid():
            return None
        files.append(path)
    return files



def safe_native_lock_files():
    """Inspect only the Gateway state-ownership native-lock directory.

    A holder may keep only a native file lock and no open SQLite handle.
    This is best-effort: no observed file descriptor is not a safe lease
    revocation verdict. Never recurse or follow symlinks.
    """
    state_dir = Path(os.environ.get(
        "OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw")))
    parents = (state_dir / "state" / "locks",
               state_dir / "state" / "locks" / "openclaw-state-owners")
    for directory in parents:
        try:
            st = directory.lstat()
        except FileNotFoundError:
            return []
        except OSError:
            return None
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_mode & 0o022):
            return None
    result = []
    try:
        # At most 128 entries: never traverse an unbounded or foreign tree.
        entries = list(parents[-1].iterdir())
        if len(entries) > 128:
            return None
        for item in entries:
            if not re.fullmatch(r"state\.[A-Za-z0-9_-]{4,128}\.lock", item.name):
                continue
            st = item.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid():
                return None
            result.append(item)
    except OSError:
        return None
    return result


def opener_pids(files):
    if files is None or not files:
        return None
    seen = set()
    for path in files:
        try:
            finished = subprocess.run(
                ["fuser", str(path)], capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if finished.returncode == 1:
            continue
        if finished.returncode != 0:
            return None
        # fuser reports holders on stdout. Never print stdout or stderr.
        words = finished.stdout.decode("ascii", "ignore").split()
        for token in words:
            if not token.isdecimal():
                return None
            pid = int(token)
            if not 0 < pid <= MAX_PID:
                return None
            seen.add(pid)
    return seen


def process_category(pid):
    if not isinstance(pid, int) or not 0 < pid <= MAX_PID:
        return "unverified"
    proc = Path("/proc") / str(pid)
    try:
        # This check cannot prove a historical PID has not been reused.
        stat_text = (proc / "stat").read_text(encoding="utf-8")
        _, _, tail = stat_text.rpartition(") ")
        state = tail.split(maxsplit=1)[0] if tail else ""
        if state in ("Z", "X", "x"):
            return "exited"
        if state not in ("R", "S", "D", "T", "t", "I"):
            return "unverified"
        args = (proc / "cmdline").read_bytes()[:16384].split(b"\x00")
    except FileNotFoundError:
        return "exited"
    except (PermissionError, OSError, UnicodeError):
        return "unverified"
    names = [item.decode("utf-8", "replace").lower() for item in args if item]
    if any("openclaw-gateway" in item for item in names):
        return "gateway_process"
    if any("openclaw.mjs" in item for item in names):
        return "openclaw_cli_or_gateway"
    return "other_process"


def service_state():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", UNIT],
            capture_output=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    value = result.stdout.strip()
    return value.decode("ascii") if value in (
        b"active", b"failed", b"inactive", b"activating") else "unknown"


def decide(pid, owner_kind, openers):
    if pid is None:
        return "logged_holder_unknown"
    if openers is None:
        return "current_owner_unverified"
    if pid in openers:
        return "logged_holder_still_has_state_file_open"
    if openers:
        return "different_sqlite_opener_observed"
    if owner_kind == "exited":
        return "historical_holder_no_current_opener"
    if owner_kind == "unverified":
        return "owner_process_unverified_no_opener"
    return "logged_pid_alive_without_sqlite_opener"


def main():
    try:
        module = previous_diagnostics()
        # Prefer the most recent safely accessible OpenClaw file log,
        # then fall back to user journald only if necessary.
        lines, source = module.file_log_sample()
        if not lines:
            lines, source = module.journal_sample()
    except (OSError, RuntimeError):
        lines, source = None, "unavailable"
    holder = holder_from_lines(lines)
    kind = process_category(holder) if holder is not None else "not_found"
    sqlite_files = safe_sqlite_files()
    native_files = safe_native_lock_files()
    # Both database handles and native file locks can enforce custody.
    # If either census is incomplete, do not claim no holder exists.
    if sqlite_files is None or native_files is None:
        openers = None
    else:
        openers = opener_pids(sqlite_files + native_files)
    verdict = decide(holder, kind, openers)
    print("gateway_service=" + service_state())
    print("contention_source=" + (
        source if source in (
            "recent_30m", "historic_tail", "private_file_tail",
            "no_user_journal", "no_safe_file_logs") else "unavailable"))
    print("logged_holder=" + ("found" if holder is not None else "not_found"))
    print("logged_holder_process=" + kind)
    print("native_lock_inventory=" + (
        "unverified" if native_files is None else
        "present" if native_files else "none_observed"))
    print("state_openers=" + (
        "unknown" if openers is None else "present" if openers else "none_observed"))
    print("logged_holder_in_state_openers=" + (
        "unknown" if holder is None or openers is None
        else "yes" if holder in openers else "no"))
    print("sqlite_owner_diagnosis=" + verdict)
    print("historical_pid_reuse_ruled_out=false")
    print("sqlite_modified=false")
    print("raw_logs_or_process_args_printed=false")
    # Status indicates complete observation, NOT authorization to start/kill.
    return 0 if verdict != "current_owner_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
