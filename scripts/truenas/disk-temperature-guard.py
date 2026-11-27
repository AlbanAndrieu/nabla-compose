#!/usr/bin/env python3
"""Mail OpenClaw when a TrueNAS hard disk crosses a temperature threshold.

Root cron every 5 minutes (reconcile-cron-jobs.py, job disk-temperature-guard).
One state per disk serial, so /dev/sdX renames after a reboot do not matter:
WARNING from 60 °C, CRITICAL from 65 °C, back to OK at 57 °C or less, and the
previous state in between. Only a state change sends a mail; the state file is
written after the mail, so a failed send is retried on the next run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

WARNING, CRITICAL, RECOVERY = 60, 65, 57
# Same directory as the hand-made check-disk-temperature.sh it replaces: no repeat alert on adoption.
STATE_DIR = Path(os.environ.get("NABLA_DISK_TEMP_STATE_DIR", "/mnt/cpool/scripts/.disk-temperature-state"))
MAIL_TO = os.environ.get("NABLA_CRON_MAIL_TO", "openclaw@albandrieu.com")


def midclt(*argv: str) -> object:
    result = subprocess.run(["midclt", "call", *argv], capture_output=True, text=True, check=True, timeout=120)
    return json.loads(result.stdout or "null")


def level(temp: float, previous: str) -> str:
    if temp >= CRITICAL:
        return "CRITICAL"
    if temp >= WARNING:
        return "WARNING"
    return "OK" if temp <= RECOVERY else previous


def message(state: str, serial: str, name: str, temp: float) -> tuple[str, str]:
    if state == "OK":
        return f"✅ [TrueNAS] Disk temperature recovered: {serial}", f"Disk {serial} ({name}) is back to {temp:.0f} °C."
    threshold = CRITICAL if state == "CRITICAL" else WARNING
    icon = "🔥" if state == "CRITICAL" else "🌡️"
    return (f"{icon} [TrueNAS] {state} disk temperature: {serial}",
            f"Disk {serial} ({name}) reached {temp:.0f} °C ({state.lower()} threshold {threshold} °C).")


def main() -> int:
    # The SSD boot disk runs hotter by design; only the raidz2 hard disks are guarded.
    disks = {d["name"]: d for d in midclt("disk.query", "[]", '{"select":["name","serial","type"]}')
             if d.get("type") == "HDD"}
    if not disks:
        return 0
    temps = midclt("disk.temperatures", json.dumps(sorted(disks)), "false") or {}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for name, value in sorted(temps.items()):
        if value is None:
            continue
        temp = float(value[0] if isinstance(value, (list, tuple)) else value)
        serial = disks.get(name, {}).get("serial") or name
        state_file = STATE_DIR / serial
        previous = state_file.read_text(encoding="utf-8").strip() if state_file.exists() else "OK"
        state = level(temp, previous)
        if state != previous:
            subject, text = message(state, serial, name, temp)
            midclt("-j", "mail.send", json.dumps({"subject": subject, "text": text, "to": [MAIL_TO]}))
            print(f"{serial}: {previous} -> {state} at {temp:.0f} °C")
        state_file.write_text(state, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
