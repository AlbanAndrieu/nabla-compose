"""DefectDojo pg_stat_activity waits: read-only sanitized metadata contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] /
          "scripts/truenas/diagnose-defectdojo-postgres-waits.py")
SPEC = importlib.util.spec_from_file_location("defectdojo_pg_waits", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_lock_wait_classifies_without_exposing_queries(monkeypatch):
    secret_text = "SELECT * FROM private_passwords"
    rows = [{
        "state": "active", "wait_type": "Lock", "wait_event": "transactionid",
        "sessions": 2, "blocked_sessions": 1,
        "oldest_query_seconds": 4800, "query": secret_text,
    }]
    seen = []
    def call(args):
        seen.append(args)
        return "nabla" if "sh" in args else json.dumps(rows)
    monkeypatch.setattr(MODULE, "execute", call)
    outcome = MODULE.inspect()
    assert outcome["state"] == "LOCK_WAIT_OBSERVED"
    assert outcome["sessions"][0]["blocked_sessions"] == 1
    assert secret_text not in json.dumps(outcome)
    assert any("pg_stat_activity" in arg for cmd in seen for arg in cmd)


def test_unavailable_postgres_is_unverified_not_healthy(monkeypatch):
    monkeypatch.setattr(MODULE, "execute", lambda args: None)
    result = MODULE.inspect()
    assert result["state"] == "UNVERIFIED"
    assert result["sql_mutated"] is False


def test_unexpected_wait_event_is_suppressed(monkeypatch):
    logs = [{"state": "active", "wait_type": "Lock",
             "wait_event": "secret\nPRIVATE", "sessions": 1,
             "blocked_sessions": 1, "oldest_query_seconds": 4}]
    monkeypatch.setattr(
        MODULE, "execute",
        lambda args: "nabla" if "sh" in args else json.dumps(logs),
    )
    outcome = MODULE.inspect()
    assert "PRIVATE" not in json.dumps(outcome)


def test_diagnostics_do_not_modify_postgres():
    assert "SELECT " in MODULE.SQL
    assert "UPDATE " not in MODULE.SQL
    assert "DELETE " not in MODULE.SQL
    assert "DROP " not in MODULE.SQL
    assert "TRUNCATE " not in MODULE.SQL
