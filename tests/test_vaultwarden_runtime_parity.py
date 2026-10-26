"""Fixtures for Vaultwarden cache vs canonical runtime secret parity."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/secrets/compare_vaultwarden_runtime_readonly.py"
SPEC = importlib.util.spec_from_file_location("vaultwarden_runtime_parity", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_secret_source_login_and_field():
    item = {
        "login": {"username": "admin", "password": "EXAMPLE_PASSWORD"},
        "fields": [{"name": "DD_DATABASE_URL", "value": "postgres://example"}],
    }
    assert MODULE.secret_value(item, {"source": "login.username"}) == "admin"
    assert MODULE.secret_value(item, {"source": "login.password"}) == "EXAMPLE_PASSWORD"
    assert MODULE.secret_value(item, {"field": "DD_DATABASE_URL"}) == "postgres://example"


def test_missing_or_duplicate_field_is_unverified():
    item = {"fields": [{"name": "PASSWORD", "value": "one"},
                       {"name": "PASSWORD", "value": "two"}]}
    assert MODULE.secret_value(item, {"field": "PASSWORD"}) is None
    assert MODULE.secret_value({}, {"source": "login.password"}) is None


@pytest.mark.parametrize(("runtime_password", "expected"), [
    ("EXAMPLE_PASSWORD", "MATCH"),
    ("MISMATCH", "DRIFT"),
    (None, "UNVERIFIED"),
])
def test_read_only_parity_reports_only_metadata(monkeypatch, runtime_password, expected):
    vault = {
        "name": "nabla/prod/defectdojo", "folderId": "folder-id",
        "login": {"username": "admin", "password": "EXAMPLE_PASSWORD"},
    }
    manifest = ({
        "server": "https://vaultwarden.example",
        "folder": {"id": "folder-id"},
    }, {
        "item": "nabla/prod/defectdojo",
        "secrets": [{"env": "DD_ADMIN_USER", "source": "login.username"},
                    {"env": "DD_ADMIN_PASSWORD", "source": "login.password"}],
    })
    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["bw", "config", "server"]:
            return "https://vaultwarden.example"
        if cmd[:2] == ["bw", "status"]:
            return '{"status":"unlocked"}'
        if cmd[:3] == ["bw", "list", "items"]:
            return json.dumps([vault])
        raise AssertionError("unsupported call")
    monkeypatch.setattr(MODULE, "expected_manifest", lambda app: manifest)
    monkeypatch.setattr(MODULE, "run", fake_run)
    monkeypatch.setattr(MODULE, "load_runtime", lambda app: {
        "DD_ADMIN_USER": "admin",
        **({"DD_ADMIN_PASSWORD": runtime_password} if runtime_password is not None else {}),
    })
    monkeypatch.setenv("BW_SESSION", "TEST_SESSION_VALUE")
    report = MODULE.check("defectdojo")
    assert report["status"] == expected
    dumped = json.dumps(report)
    assert "EXAMPLE_PASSWORD" not in dumped
    assert "TEST_SESSION_VALUE" not in dumped
    assert "RUNTIME_PASSWORD" not in dumped
    assert report["runtime_modified"] is False
    assert report["vault_modified"] is False


@pytest.mark.parametrize(("folder_search", "global_search", "expected"), [
    ([], [], "VAULT_ITEM_MISSING"),
    ([], [{"name": "nabla/prod/code", "folderId": "different"}],
     "VAULT_ITEM_IN_OTHER_FOLDER"),
    ([], [{"name": "nabla/prod/code", "folderId": "one"},
          {"name": "nabla/prod/code", "folderId": "two"}],
     "VAULT_ITEM_DUPLICATED_OUTSIDE_EXPECTED_FOLDER"),
    ([{"name": "nabla/prod/code", "folderId": "folder-id"}] * 2, [],
     "VAULT_ITEM_DUPLICATED_IN_FOLDER"),
])
def test_missing_misplaced_and_duplicated_vault_items_are_distinct(
    monkeypatch, folder_search, global_search, expected,
):
    manifest = ({"server": "https://vaultwarden.example",
                 "folder": {"id": "folder-id"}},
                {"item": "nabla/prod/code", "secrets": [
                    {"env": "PASSWORD", "field": "CODE_PASSWORD"}]})
    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["bw", "config", "server"]:
            return "https://vaultwarden.example"
        if cmd[:2] == ["bw", "status"]:
            return '{"status":"unlocked"}'
        if cmd[:3] == ["bw", "list", "items"]:
            return json.dumps(folder_search if "--folderid" in cmd else global_search)
        raise AssertionError("unexpected bw call")
    monkeypatch.setattr(MODULE, "expected_manifest", lambda app: manifest)
    monkeypatch.setattr(MODULE, "run", fake_run)
    monkeypatch.setenv("BW_SESSION", "TEST_SESSION")
    report = MODULE.check("code")
    assert report["status"] == "UNVERIFIED"
    assert report["reason"] == expected
    assert "folder-id" not in json.dumps(report)


def test_empty_vault_password_has_explicit_redacted_reason(monkeypatch):
    vault = {"name": "nabla/prod/defectdojo", "folderId": "f",
             "login": {"username": "nabla", "password": None}}
    manifest = ({"server": "https://vault.example", "folder": {"id": "f"}},
                {"item": "nabla/prod/defectdojo", "secrets": [
                    {"env": "DD_ADMIN_PASSWORD", "source": "login.password"},
                    {"env": "DD_ADMIN_USER", "source": "login.username"}]})
    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["bw", "config", "server"]:
            return "https://vault.example"
        if cmd[:2] == ["bw", "status"]:
            return '{"status":"unlocked"}'
        if cmd[:3] == ["bw", "list", "items"]:
            return json.dumps([vault])
        raise AssertionError("unexpected bw call")
    monkeypatch.setattr(MODULE, "expected_manifest", lambda app: manifest)
    monkeypatch.setattr(MODULE, "run", fake_run)
    monkeypatch.setattr(MODULE, "load_runtime", lambda app: {
        "DD_ADMIN_USER": "admin", "DD_ADMIN_PASSWORD": "DO_NOT_LOG_VALUE",
    })
    monkeypatch.setenv("BW_SESSION", "TEST_SESSION")
    report = MODULE.check("defectdojo")
    assert report["status"] == "DRIFT"
    assert report["keys"]["DD_ADMIN_USER"] == "DRIFT"
    assert report["keys"]["DD_ADMIN_PASSWORD"] == "UNVERIFIED"
    assert report["unverified_reasons"]["DD_ADMIN_PASSWORD"] == "VAULT_FIELD_MISSING_OR_EMPTY"
    assert "DO_NOT_LOG_VALUE" not in json.dumps(report)


def test_missing_session_fails_without_vault_access(monkeypatch):
    monkeypatch.setenv("BW_SESSION", "")
    monkeypatch.setattr(MODULE, "run", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("should not invoke bw")
    ))
    result = MODULE.check("defectdojo")
    assert result["status"] == "UNVERIFIED"


def test_source_never_executes_vault_writes_or_root_python():
    source = SOURCE.read_text()
    assert '"sudo", "-n", "cat", "--", path' in source
    assert '"bw", "list", "items"' in source
    for fragment in ('"bw", "edit"', '"bw", "create"', '"bw", "sync"',
                     'app.redeploy', 'materialize_runtime.py --install'):
        assert fragment not in source
