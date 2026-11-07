"""Services whose PID 1 accumulated zombies on TrueNAS must run an init process.

The 2026-11-04 diagnostic (`scripts/truenas/diagnose-performance.sh`) attributed
~1,400 zombies to these containers: their main process never reaps orphaned
healthcheck or cron children. `init: true` makes Docker's tini PID 1.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

REAPED_SERVICES = {
    "bichon": "bichon",
    "clickhouse": "clickhouse",
    "drawio": "drawio",
    "kafka": "kafka",
    "minio": "minio",
    "mongo": "mongo",
    "ollama": "ollama",
    "openwebui": "openwebui",
    "sentry-clickhouse": "sentry-clickhouse",
    "suricata": "suricata",
}


@pytest.mark.parametrize(("app", "service"), sorted(REAPED_SERVICES.items()))
def test_service_runs_an_init_process(app: str, service: str) -> None:
    document = yaml.safe_load((ROOT / "apps" / app / "compose.yml").read_text(encoding="utf-8"))
    assert document["services"][service].get("init") is True
