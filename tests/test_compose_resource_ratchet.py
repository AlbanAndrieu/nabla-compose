"""Every service rotates its logs; services without a memory limit may only decrease.

TrueNAS performance plan of 16/11 (docs/roadmap.md, items 6 and 8): Docker
keeps json-file logs without rotation on TrueNAS, so each file shares the
`x-logging: &nabla-logging` anchor. Memory limits come from memory.peak x 1.5;
lower the ceiling when you cap an existing service.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_WITHOUT_MEMORY_LIMIT = 132


def _services() -> list[dict]:
    files = subprocess.run(
        ["git", "ls-files", "apps/*/compose.yml"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    found = []
    for compose in files:
        data = yaml.safe_load((ROOT / compose).read_text(encoding="utf-8")) or {}
        found.extend(service or {} for service in (data.get("services") or {}).values())
    return found


def test_services_without_memory_limit_do_not_grow():
    missing = [
        s
        for s in _services()
        if not (s.get("mem_limit") or s.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory"))
    ]
    assert len(missing) <= MAX_WITHOUT_MEMORY_LIMIT


def test_every_service_rotates_its_logs():
    missing = [s for s in _services() if not s.get("logging", {}).get("options", {}).get("max-size")]
    assert not missing
