"""Offline Scrutiny, Prometheus bind and TrueNAS app lifecycle regressions."""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    source = ROOT / path
    spec = importlib.util.spec_from_file_location(source.stem.replace("-", "_"), source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scrutiny_renderer_keeps_only_canonical_env():
    compose = (ROOT / "apps/scrutiny/compose.yml").read_text()
    script = (ROOT / "scripts/truenas/deploy-scrutiny.sh").read_text()
    assert "/mnt/cpool/secrets/runtime/scrutiny/.env.secrets" in compose
    assert "/mnt/cpool/scrutiny/.env.secrets" not in compose
    assert script.count('verify_scrutiny_compose_secret_path "${scrutiny_compose}"') == 2
    assert "Reconciling stored TrueNAS Scrutiny Custom App" in script


def test_log_triage_recent_groups_and_redacts():
    module = load("scripts/truenas/triage-app-lifecycle-log.py")
    log = "\n".join((
        "[2026/09/08 20:41:51] (ERROR) Failed 'up' action for 'scrutiny' app: unhealthy secret=PRIVATE",
        "[2026/10/26 20:01:24] (ERROR) Failed 'up' action for 'prometheus' app: "
        "invalid mount config: bind source path does not exist: "
        "/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key token=HIDDEN",
        "[2026/10/26 20:01:33] (ERROR) Failed 'up' action for 'scrutiny' app: "
        "env file /mnt/cpool/scrutiny/.env.secrets not found secret=NEVER_LEAK",
        "[2026/10/23 06:41:18] (ERROR) Failed 'up' action for 'litellm' app: "
        "env file /mnt/cpool/secrets/runtime/litellm/.env.secrets not found",
    ))
    report = module.summarize(log, date(2026, 10, 20))
    assert report["events_recent"] == 3
    assert report["events_historical_excluded"] == 1
    assert report["categories"] == {
        "missing_runtime_env": 1,
        "prometheus_metrics_bind": 1,
        "scrutiny_legacy_secret": 1,
    }
    assert {row["app"] for row in report["apps"]} == {"litellm", "scrutiny", "prometheus"}
    assert all(row["runtime"] == "NOT_VERIFIED" for row in report["apps"])
    assert not any(secret in json.dumps(report) for secret in ("PRIVATE", "HIDDEN", "NEVER_LEAK"))


@pytest.mark.parametrize(("message", "expected"), [
    ("dependency failed to start: container scrutiny is unhealthy", "dependency_unhealthy"),
    ("tried to kill container but did not receive an exit event", "docker_stop_exit_event_missing"),
    ("manifest unknown: not found", "registry_manifest_missing"),
    ("service sentry-migrate didn't complete successfully: exit 1", "migration_or_dependency_exit"),
    ("Timed out waiting for response", "lifecycle_timeout"),
])
def test_other_error_categories(message, expected):
    module = load("scripts/truenas/triage-app-lifecycle-log.py")
    assert module.error_class("app", message) == expected


def test_log_symlink_is_rejected(tmp_path: Path):
    module = load("scripts/truenas/triage-app-lifecycle-log.py")
    target = tmp_path / "log"
    target.write_text("PRIVATE")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        module.bounded_log(link)


def test_private_metrics_directory_is_installed_only_when_missing(tmp_path: Path):
    module = load("scripts/truenas/reconcile-fastapi-metrics-credential.py")
    source = tmp_path / "sample.env"
    source.write_text("METRICS_SCRAPE_KEY=" + "a" * 64 + "\n")
    source.chmod(0o600)
    parent = tmp_path / "prometheus"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    dest = parent / "secrets" / "fastapi-sample-metrics.key"
    assert module.inspect(source, dest, require_root=False) == "destination_directory_unavailable"
    if os.geteuid() != 0:
        pytest.skip("TrueNAS root-only installer requires real root for integration test")
    assert module.install(source, dest) == "credential_ready"
    assert dest.parent.stat().st_gid == module.EXPECTED_GID
    assert (dest.parent.stat().st_mode & 0o777) == 0o750
    assert (dest.stat().st_mode & 0o777) == 0o640
    assert module.install(source, dest) == "credential_ready"


def test_missing_parent_tree_not_created(tmp_path: Path):
    module = load("scripts/truenas/reconcile-fastapi-metrics-credential.py")
    source = tmp_path / "sample.env"
    source.write_text("METRICS_SCRAPE_KEY=" + "a" * 64 + "\n")
    source.chmod(0o600)
    dest = tmp_path / "uncreated-parent" / "secrets" / "token"
    if os.geteuid() != 0:
        pytest.skip("TrueNAS root-only installer requires real root")
    with pytest.raises(ValueError):
        module.install(source, dest)
    assert not dest.parent.parent.exists()


def test_destination_symlink_is_refused(tmp_path: Path):
    module = load("scripts/truenas/reconcile-fastapi-metrics-credential.py")
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        module.prepare_destination_directory(link / "token.key")


def test_bind_remains_explicit_and_no_key_is_generated():
    compose = (ROOT / "apps/prometheus/compose.yml").read_text()
    installer = (ROOT / "scripts/truenas/reconcile-fastapi-metrics-credential.py").read_text()
    assert "create_host_path: false" in compose
    assert "/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key" in compose
    assert "secrets.token_hex" not in installer
    assert "prepare_destination_directory(dest)" in installer
    assert "I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL" in installer
