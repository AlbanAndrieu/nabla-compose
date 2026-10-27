"""Offline tests for existing DefectDojo admin credential recovery.

The mocked docker interaction never contacts a container or leaks a password.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(tmp_path: Path, username="admin", passwd="dummy-existing-password-123"):
    f = tmp_path / "env.secrets"
    f.write_text(
        f"DD_ADMIN_USER={username}\nDD_ADMIN_PASSWORD='{passwd}'\n"
        "DD_SECRET_KEY=unchanged-unrelated\n",
        encoding="utf-8",
    )
    f.chmod(0o600)
    return f


def test_password_parser_hides_unrelated_secrets(tmp_path):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    output = module.parse_runtime_secret(source(tmp_path), require_root_metadata=False)
    assert output == {
        "DD_ADMIN_USER": "admin",
        "DD_ADMIN_PASSWORD": "dummy-existing-password-123",
    }
    assert "DD_SECRET_KEY" not in output


@pytest.mark.parametrize(("username", "password", "category"), [
    ("nabla", "dummy-existing-password-123", "SOURCE_USERNAME_NOT_EXISTING_ADMIN"),
    ("admin", "tiny", "SOURCE_PASSWORD_LENGTH_INVALID"),
])
def test_existing_admin_target_and_password_contract(tmp_path, username, password, category):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    f = source(tmp_path, username=username, passwd=password)
    with pytest.raises(ValueError, match=category):
        module.parse_runtime_secret(f, require_root_metadata=False)


def test_duplicate_password_is_rejected(tmp_path):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    file = source(tmp_path)
    file.write_text(file.read_text() + "\nDD_ADMIN_PASSWORD=second\n")
    with pytest.raises(ValueError, match="SOURCE_DUPLICATE_KEY"):
        module.parse_runtime_secret(file, require_root_metadata=False)


def test_source_symlink_is_rejected(tmp_path):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    file = source(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(file)
    with pytest.raises(ValueError, match="SOURCE_SYMLINK"):
        module.parse_runtime_secret(link, require_root_metadata=False)


@pytest.mark.parametrize(("mode", "expected"), [
    ("check", "PASSWORD_MATCH"), ("check", "PASSWORD_MISMATCH"),
    ("apply", "PASSWORD_UPDATED"), ("apply", "ACCOUNT_NOT_UNIQUE_OR_ABSENT"),
])
def test_django_credential_only_via_stdin_and_output_sanitized(monkeypatch, mode, expected):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    calls = []

    def fake_run(cmd, *, input, **kw):
        calls.append((cmd, input, kw))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"state": expected}))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.run_django({
        "DD_ADMIN_USER": "admin",
        "DD_ADMIN_PASSWORD": "existing-secret-never-log",
    }, mode)
    assert result == expected
    cmd, input_data, kwargs = calls[0]
    assert "existing-secret-never-log" not in str(cmd)
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert json.loads(input_data)["password"] == "existing-secret-never-log"


def test_initializer_can_sync_existing_admin_before_uwsgi(monkeypatch):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    calls = []

    def fake_run(cmd, *, input, **kwargs):
        calls.append((cmd, input))
        return SimpleNamespace(returncode=0, stdout='{"state":"PASSWORD_UPDATED"}')

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    credentials = {"DD_ADMIN_USER": "admin", "DD_ADMIN_PASSWORD": "TEST_PASSWORD_PRIVATE"}
    assert module.run_django(credentials, "apply", "defectdojo-initializer") == "PASSWORD_UPDATED"
    command, payload = calls[0]
    assert command[:4] == ["docker", "exec", "-i", "defectdojo-initializer"]
    assert "TEST_PASSWORD_PRIVATE" not in str(command)
    assert json.loads(payload)["password"] == "TEST_PASSWORD_PRIVATE"


def test_unknown_container_is_not_executed(monkeypatch):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("no exec allowed")))
    assert module.run_django(
        {"DD_ADMIN_USER": "admin", "DD_ADMIN_PASSWORD": "TEST"},
        "apply", "postgres",
    ) == "DJANGO_UNAVAILABLE"


def test_nonjson_django_output_is_unverified(monkeypatch):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    monkeypatch.setattr(module.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="not json"))
    assert module.run_django({
        "DD_ADMIN_USER": "admin", "DD_ADMIN_PASSWORD": "dummy",
    }, "check") == "DJANGO_RESPONSE_UNVERIFIED"


def test_apply_cannot_run_without_ack(monkeypatch):
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    with pytest.raises(SystemExit):
        module.main(["--apply"])


def test_metadata_inspector_recognizes_copied_template(tmp_path):
    module = load("scripts/truenas/prepare-defectdojo-runtime-env.py")
    contents = (ROOT / "apps/defectdojo/.env.example").read_text()
    file = tmp_path / "env"
    file.write_text(contents)
    file.chmod(0o600)
    # A user-owned copy is correctly classified as needing metadata repair.
    if file.stat().st_uid != 0:
        assert module.inspect(file) == "METADATA_PERMISSIONS_INVALID"
    else:
        assert module.inspect(file) == "READY"
    file.write_text(contents + "\nDD_ADMIN_PASSWORD=must-not-be-here\n")
    assert module.inspect(file) == "METADATA_INVALID"


def test_metadata_inspector_does_not_touch_secret_file(tmp_path, monkeypatch):
    module = load("scripts/truenas/prepare-defectdojo-runtime-env.py")
    root = tmp_path / "secret-root"
    root.mkdir()
    secret = root / ".env.secrets"
    secret.write_text("DD_SECRET_KEY=private")
    target = root / ".env"
    target.write_text(module.CONTENTS)
    target.chmod(0o600)
    assert module.inspect(target) in ("READY", "METADATA_PERMISSIONS_INVALID")
    assert secret.read_text() == "DD_SECRET_KEY=private"


def test_core_django_code_changes_existing_password_only():
    module = load("scripts/truenas/reconcile-defectdojo-admin-password.py")
    assert "user.set_password(secret)" in module.DJANGO
    assert 'user.save(update_fields=["password"])' in module.DJANGO
    assert "objects.create" not in module.DJANGO
    assert "createsuperuser" not in module.DJANGO
