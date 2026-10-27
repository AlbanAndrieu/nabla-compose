"""Fixture-only verification of DefectDojo shared-PostgreSQL reset inventory."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/inspect-defectdojo-db-reset.py"
SPEC = importlib.util.spec_from_file_location("defectdojo_db_reset_inspector", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def mock_inventory(monkeypatch, *, count=0, sessions=0, missing=False, owner="defectdojo"):
    import json

    monkeypatch.setattr(MODULE, "postgres_admin", lambda: "postgres")

    def fake_sql(_user, db, sql):
        if db == "postgres":
            return json.dumps({
                "exists": True, "owner": owner,
                "active_sessions": sessions, "database_bytes": 1000000,
            })
        if "to_regclass" in sql:
            return "f" if missing else "t"
        if "count(*)" in sql:
            return str(count)
        raise AssertionError("unexpected SQL query")

    monkeypatch.setattr(MODULE, "sql", fake_sql)


def test_unused_database_candidate_is_read_only(monkeypatch):
    mock_inventory(monkeypatch)
    report = MODULE.inspect()
    assert report["reset_candidate"] is True
    assert report["active_sessions"] == 0
    assert set(report["business_table_counts"]) == set(MODULE.BUSINESS_TABLES)
    assert all(n == 0 for n in report["business_table_counts"].values())


@pytest.mark.parametrize("options", [
    {"count": 1}, {"sessions": 1}, {"missing": True}, {"owner": "other"},
])
def test_nonempty_or_connected_database_not_reset_candidate(monkeypatch, options):
    mock_inventory(monkeypatch, **options)
    assert MODULE.inspect()["reset_candidate"] is False


def test_query_uses_only_static_database_and_psql(monkeypatch):
    recorded = []

    def fake_run(args):
        recorded.append(args)
        return "0"

    monkeypatch.setattr(MODULE, "run", fake_run)
    MODULE.sql("postgres", "defectdojo", "SELECT 0")
    args = recorded[0]
    assert args[:4] == ["docker", "exec", MODULE.CONTAINER, "psql"]
    assert "SELECT 0" in args
    assert all("password" not in x.lower() for x in args)


def test_no_drop_delete_or_create_in_inspection_sql():
    source = SOURCE.read_text()
    assert '"DROP DATABASE"' not in source
    assert '"DELETE FROM"' not in source
    assert '"CREATE DATABASE"' not in source
    assert "subprocess.run" in source
    assert "postgres_admin" in source
