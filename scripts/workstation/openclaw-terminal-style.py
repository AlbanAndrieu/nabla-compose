#!/usr/bin/env python3
"""Terminal-only decoration of sanitized OpenClaw diagnostics.

Keep stdout byte-for-byte compatible without a TTY, under NO_COLOR,
or with OPENCLAW_COLOR=never. Never decorate JSON or extract secret values.
"""
from __future__ import annotations

import os
import sys

RESET = "\x1b[0m"
COLORS = {"ok": "\x1b[32m", "warn": "\x1b[33m", "bad": "\x1b[31m", "info": "\x1b[36m"}
ICONS = {"ok": "✅", "warn": "⚠️", "bad": "❌", "info": "ℹ️"}


def enabled() -> bool:
    setting = os.environ.get("OPENCLAW_COLOR", "auto").lower()
    if os.environ.get("NO_COLOR") is not None or setting == "never":
        return False
    return setting == "always" or (sys.stdout.isatty() and os.environ.get("TERM") != "dumb")


def status(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("{", "}", "[", "]", '"')):
        return None
    upper = stripped.upper()
    if upper.startswith(("ERROR:", "ERROR ", "FAIL:", "FAIL ")):
        return "bad"
    if upper.startswith("ACTION:"):
        return "warn"
    if upper.startswith(("WARN", "NOTE:")):
        return "warn" if upper.startswith("WARN") else "info"
    if upper.startswith(("OK ", "VERIFIED ", "CREATED ", "RESTORE_TEST_OK")):
        return "ok"
    if stripped.startswith("==>"):
        return "info"
    if "=" not in stripped:
        return None
    name, value = stripped.split("=", 1)
    name, value = name.strip().lower(), value.strip().lower()
    if name.startswith(("failure_", "litellm_budget_", "embedding_auth_", "context_over_budget_", "context_pressure", "memory_sync_aborted", "gateway_connection_refused", "status_non_ok")):
        if value.isdigit() and int(value) > 0 :
            return "bad"
        return "ok" if value == "0" else None
    if name.startswith(("health_liveliness_http", "health_readiness_http")):
        return "ok" if value == "200" else "bad" if value != "unreachable" else "warn"
    if name == "key" and " http=" in value:
        code = value.rsplit(" http=", 1)[-1]
        return "ok" if code == "200" else "warn" if code == "unreachable" else "bad"
    if name == "proxy":
        return "info"
    if name == "budget_usage_pct":
        if value == "not_reported":
            return "warn"
        try:
            fraction = float(value)
        except ValueError:
            return None
        return "bad" if fraction >= 100 else "warn" if fraction >= 80 else "ok"
    if name in ("max_budget", "tpm_limit", "rpm_limit"):
        return "warn" if value == "not_reported" else "info"
    if name.startswith("admin_audit") and value.startswith("skipped"):
        return "warn"
    if name in ("heartbeat_recent_failed", "heartbeat_consecutive_failures_at_head"):
        return "bad" if value.isdigit() and int(value) > 0 else "ok" if value == "0" else None
    if name == "heartbeat_last_status":
        return "ok" if value == "ok" else "bad" if value == "error" else None
    if name == "sqlite_integrity_ok":
        return "ok" if value.isdigit() and int(value) > 0 else None
    if name == "openai_cli_key_parity":
        return "ok" if value == "match" else "bad"
    if value in ("unbalanced_quotes", "unbalanced_quotes_or_reference", "mismatch", "unexpanded_reference"):
        return "bad"
    if value in ("ready", "healthy", "match"):
        return "ok"
    return None


def decorate(line: str, color: bool) -> str:
    if not color:
        return line
    kind = status(line)
    if kind is None:
        return line
    return f"{COLORS[kind]}{ICONS[kind]} {line.rstrip(chr(10))}{RESET}" + ("\n" if line.endswith("\n") else "")


def main() -> None:
    color = enabled()
    for line in sys.stdin:
        sys.stdout.write(decorate(line, color))


if __name__ == "__main__":
    main()
