#!/usr/bin/env python3
"""Classify a failed OpenClaw user Gateway using systemd and journald.

Read-only, fixed allowlist. NEVER print raw journal records, environment,
command arguments, configuration, paths, tokens or process details.
No repair, restart, npm update, backup, SQLite access or LLM calls.
"""
from __future__ import annotations

import re
import subprocess

UNIT = "openclaw-gateway.service"
FIELDS = ("ActiveState", "SubState", "Result", "ExecMainCode",
          "ExecMainStatus", "NRestarts")
MAX_JOURNAL_BYTES = 131072
MAX_JOURNAL_LINES = 160
SAFE_STATE = {"active", "inactive", "failed", "activating", "deactivating"}
SAFE_RESULT = {"success", "exit-code", "signal", "core-dump", "timeout",
               "watchdog", "start-limit-hit", "oom-kill", "resources", "protocol"}
SAFE_SUBSTATE = {"running", "dead", "failed", "start", "start-pre", "start-post",
                 "auto-restart", "exited", "stop", "stop-sigterm",
                 "stop-sigkill", "stop-post"}

# Interpret these only as journal *hints*, not verified root causes.
PATTERNS = (
    ("state_owner_contention",
     (r"GatewayStateOwnerContentionError", r"state database is busy",
      r"SQLITE_BUSY", r"database is locked")),
    ("state_migration",
     (r"schema migration (failed|pending|error)", r"migration.*rollback",
      r"(sqlite|database).*migration.*(failed|error)")),
    ("node_runtime",
     (r"EBADENGINE", r"preflight-node-runtime-incompatible",
      r"requires Node", r"unsupported Node.js")),
    ("port_conflict", (r"EADDRINUSE", r"address already in use")),
    ("missing_dependency",
     (r"ERR_MODULE_NOT_FOUND", r"MODULE_NOT_FOUND",
      r"Cannot find module", r"Cannot find package")),
    ("filesystem_permission", (r"\bEACCES\b", r"\bEPERM\b", r"permission denied")),
    ("configuration", (r"config.*(invalid|failed validation|parse error)",
                       r"OPENCLAW_CONFIG_PATH.*(missing|invalid)")),
    ("plugin_initialization",
     (r"plugin.*(migration failed|initialization failed|load failed)",
      r"CLI descriptor load failed", r"plugin reload failed")),
    ("authentication",
     (r"SecretRef.*(unavailable|failed)", r"credential.*(missing|rejected)")),
    ("out_of_memory", (r"out of memory", r"ENOMEM", r"heap out of memory")),
)


def run(command, timeout=8):
    try:
        result = subprocess.run(command, capture_output=True, check=False,
                                timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None, b""
    return result.returncode, result.stdout[:MAX_JOURNAL_BYTES]


def systemd_properties():
    args = ["systemctl", "--user", "show", UNIT, "--no-pager"]
    args.extend("-p" + field for field in FIELDS)
    rc, raw = run(args)
    if rc != 0:
        return None
    result = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        key, equal, value = line.partition("=")
        if equal and key in FIELDS:
            result[key] = value.strip()
    return result


def current_unit_matches_expected():
    rc, raw = run(["systemctl", "--user", "show", UNIT,
                   "-p", "ExecStart", "--value"])
    if rc != 0 or not raw or len(raw) >= MAX_JOURNAL_BYTES:
        return "unverified"
    # This is a closed check of the previously agreed service binding.
    # Do not expose the actual path, flags or ExecStart data to stdout.
    text = raw.decode("utf-8", "replace")
    node = "/.local/share/mise/installs/node/24.22.1/bin/node"
    package = ("/.local/share/mise/installs/node/24.22.1"
               "/lib/node_modules/openclaw/openclaw.mjs")
    if (node in text and package in text and
            "gateway --port 18789" in text):
        return "target_binding_confirmed"
    return "different_or_unverified"


def journal_sample():
    # No subprocess shell, no raw log export and no state-file reads.
    rc, data = run(["journalctl", "--user", "--unit", UNIT,
                    "--since", "-30 minutes", "--lines", str(MAX_JOURNAL_LINES),
                    "--no-pager", "--output", "cat"])
    if rc != 0:
        return None
    return data.decode("utf-8", "replace").splitlines()[-MAX_JOURNAL_LINES:]


def classify_journal(lines):
    if lines is None:
        return "journal_unavailable"
    if not lines:
        return "no_recent_journal_evidence"
    text = "\n".join(lines)
    for label, regexes in PATTERNS:
        if any(re.search(expr, text, re.IGNORECASE) for expr in regexes):
            return label
    return "no_known_pattern"


def safe_enum(value, allowed):
    return value if value in allowed else "unknown"


def safe_number(value):
    if not isinstance(value, str) or not value.isdecimal():
        return "unknown"
    number = int(value)
    return str(number) if 0 <= number <= 9999 else "unknown"


def main():
    properties = systemd_properties()
    journal = journal_sample()
    if properties is None:
        print("service_properties=unavailable")
        print("service_state=unknown")
        print("service_result=unknown")
        print("service_exit_status=unknown")
        print("service_restart_count=unknown")
    else:
        print("service_properties=available")
        print("service_state=" +
              safe_enum(properties.get("ActiveState"), SAFE_STATE))
        print("service_substate=" +
              safe_enum(properties.get("SubState"), SAFE_SUBSTATE))
        print("service_result=" +
              safe_enum(properties.get("Result"), SAFE_RESULT))
        print("service_exit_status=" +
              safe_number(properties.get("ExecMainStatus")))
        print("service_restart_count=" +
              safe_number(properties.get("NRestarts")))
    print("service_target_binding=" + current_unit_matches_expected())
    print("journal_pattern=" + classify_journal(journal))
    print("journal_lines_inspected=" + str(len(journal) if journal is not None else 0))
    print("raw_journal_or_environment_printed=false")
    # Triage is observational; a failed service is never reported as healthy.
    return 0 if properties is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
