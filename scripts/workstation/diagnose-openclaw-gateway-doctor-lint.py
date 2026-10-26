#!/usr/bin/env python3
"""Read-only structured OpenClaw Doctor diagnosis for Gateway exit 78.

Use the already-selected managed package under pinned Node 24.22.1.
Never apply migrations, repairs, updates, or print Doctor's raw messages.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess

VERSION = "2026.10.7"
NODE_VERSION = "24.22.1"
REPORT_LIMIT = 1024 * 1024
TIMEOUT = 90

CATEGORIES = (
    ("gateway_config", ("gateway-config", "config-validation", "gateway.mode")),
    ("schema_migration", ("migration", "schema", "database", "state-sqlite")),
    ("plugin", ("plugin", "extension")),
    ("auth", ("auth", "credential", "secret")),
    ("session_storage", ("session", "storage")),
)


def installation():
    root = Path.home() / ".local/share/mise/installs/node" / NODE_VERSION
    return root / "bin/node", root / "lib/node_modules/openclaw/openclaw.mjs"


def owner_only_file(path):
    try:
        st = path.lstat()
        return (stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
                and not st.st_mode & 0o022)
    except OSError:
        return False


def extract_json(raw):
    """Accept leading CLI warnings without displaying them."""
    if len(raw) > REPORT_LIMIT:
        return None
    source = raw.decode("utf-8", "replace")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", source):
        try:
            value, consumed = decoder.raw_decode(source[match.start():])
        except (ValueError, UnicodeError):
            continue
        if isinstance(value, dict) and (
            isinstance(value.get("findings"), list) or
            value.get("schemaVersion") == 1
        ):
            return value
    return None


def safe_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 50000 else "unknown"


def category(finding):
    check_id = finding.get("checkId")
    path = finding.get("path")
    if not isinstance(check_id, str) or len(check_id) > 200:
        return "other"
    haystack = check_id.lower()
    if isinstance(path, str) and path in ("gateway.mode", "gateway.bind",
                                         "gateway.auth.mode", "gateway.port"):
        haystack += " gateway-config"
    for label, needles in CATEGORIES:
        if any(word in haystack for word in needles):
            return label
    return "other"


def severity(finding):
    value = finding.get("severity")
    return value if value in ("error", "warning", "info") else "unknown"


def issue_category(report):
    """Return only fixed codes based on structured ids and error markers."""
    if not isinstance(report, dict):
        return "report_unavailable"
    findings = report.get("findings")
    if not isinstance(findings, list):
        return "report_unavailable"
    categories = {category(row) for row in findings[:200]
                  if isinstance(row, dict) and severity(row) in ("error", "warning")}
    if "gateway_config" in categories:
        return "gateway_config"
    if "schema_migration" in categories:
        return "schema_migration"
    if "plugin" in categories:
        return "plugin"
    if "auth" in categories:
        return "auth"
    if "session_storage" in categories:
        return "session_storage"
    if categories:
        return "other_findings"
    return "no_reported_findings"


def run_doctor():
    node, entry = installation()
    if not owner_only_file(node) or not owner_only_file(entry):
        print("doctor_runtime=unverified")
        return 2
    env = dict(os.environ)
    home = str(Path.home())
    env.setdefault("OPENCLAW_STATE_DIR", home + "/.openclaw")
    env.setdefault("OPENCLAW_CONFIG_PATH", env["OPENCLAW_STATE_DIR"] + "/openclaw.json")
    env.setdefault("OPENCLAW_WORKSPACE_DIR", env["OPENCLAW_STATE_DIR"] + "/workspace")
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    # Explicit --lint is the documented non-mutating posture.
    cmd = [str(node), str(entry), "doctor", "--lint", "--json"]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True,
                              timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        print("doctor_runtime=failed_or_timeout")
        return 2
    report = extract_json(proc.stdout[:REPORT_LIMIT + 1])
    print("doctor_runtime=executed")
    print("doctor_exit=" + (str(proc.returncode) if proc.returncode in (0, 1, 2)
                            else "other"))
    if report is None:
        print("doctor_report=unavailable")
        print("doctor_diagnosis=report_unavailable")
        print("doctor_raw_output_printed=false")
        return 2

    rows = report.get("findings", [])
    if not isinstance(rows, list):
        rows = []
    print("doctor_report=structured")
    print("doctor_schema=" + ("1" if report.get("schemaVersion") == 1 else "unknown"))
    print("doctor_checks_run=" + str(safe_count(report.get("checksRun"))))
    print("doctor_findings_count=" + str(len(rows)) if len(rows) <= 50000 else "doctor_findings_count=unknown")
    print("doctor_diagnosis=" + issue_category(report))
    if report.get("ok") is True:
        print("doctor_ok=yes")
    elif report.get("ok") is False:
        print("doctor_ok=no")
    else:
        print("doctor_ok=unknown")
    for label in ("gateway_config", "schema_migration", "plugin",
                  "auth", "session_storage", "other"):
        amount = sum(1 for row in rows[:200] if isinstance(row, dict) and
                     category(row) == label and severity(row) in ("error", "warning"))
        print("doctor_" + label + "_findings=" + str(amount))
    print("doctor_raw_output_printed=false")
    print("doctor_repairs_performed=false")
    # This is a diagnostic; code 0 indicates a complete structured report,
    # not a healthy or migrated Gateway.
    return 0


if __name__ == "__main__":
    raise SystemExit(run_doctor())
