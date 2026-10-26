"""Offline security contracts for FastAPI → Prometheus scrape credentials.

Never requires the operator secret, a Docker socket or access to TrueNAS.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/truenas/reconcile-fastapi-metrics-credential.py"
SPEC = importlib.util.spec_from_file_location("fastapi_metrics_scrape", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_parse_single_hex_256bit_key_without_logging() -> None:
    key = "abcdef0123456789" * 4
    source = ("OTHER_SECRET=never-print\nMETRICS_SCRAPE_KEY=" + key + "\n").encode()
    assert module.parse_key(source) == key.encode()
    assert module.parse_key(("METRICS_SCRAPE_KEY='" + key + "'\n").encode()) == key.encode()


@pytest.mark.parametrize("source", [
    b"OTHER_SECRET=value\n",
    b"METRICS_SCRAPE_KEY=short\n",
    b"METRICS_SCRAPE_KEY=literal-secret\n",
    b"METRICS_SCRAPE_KEY=" + b"a" * 64 + b"\nMETRICS_SCRAPE_KEY=" + b"a" * 64 + b"\n",
    b"METRICS_SCRAPE_KEY=" + b"x" * 64 + b"\n",
])
def test_parse_refuses_missing_ambiguous_or_non_256bit_key(source: bytes) -> None:
    with pytest.raises(ValueError):
        module.parse_key(source)


def private_source(tmp_path: Path, key: str = "a" * 64) -> Path:
    source = tmp_path / "source.env"
    source.write_text("OTHER_KEY=sensitive\nMETRICS_SCRAPE_KEY=" + key + "\n")
    source.chmod(0o600)
    return source


def test_check_read_only_until_credential_installed(tmp_path: Path) -> None:
    source = private_source(tmp_path)
    directory = tmp_path / "prometheus"
    directory.mkdir(mode=0o700)
    target = directory / "fastapi-sample-metrics.key"
    assert module.inspect(source, target, require_root=False) == "credential_not_installed"
    assert not target.exists()
    target.write_text("a" * 64 + "\n")
    target.chmod(0o640)
    assert module.inspect(source, target, require_root=False) == "credential_ready"
    target.write_text("b" * 64 + "\n")
    assert module.inspect(source, target, require_root=False) == "credential_mismatch"


def test_private_source_and_destination_symlinks_fail_closed(tmp_path: Path) -> None:
    source = private_source(tmp_path)
    destdir = tmp_path / "secrets"
    destdir.mkdir(mode=0o700)
    target = destdir / "scrape.key"
    target.symlink_to(source)
    assert module.inspect(source, target, require_root=False) == "destination_symlink_refused"
    source_link = tmp_path / "source-link.env"
    source_link.symlink_to(source)
    assert module.inspect(source_link, target, require_root=False) == "source_missing_insecure_or_invalid"


def test_source_world_readable_and_destination_writable_are_refused(tmp_path: Path) -> None:
    source = private_source(tmp_path)
    directory = tmp_path / "prometheus"
    directory.mkdir(mode=0o700)
    target = directory / "scrape.key"
    target.write_text("a" * 64 + "\n")
    target.chmod(0o640)
    source.chmod(0o644)
    assert module.inspect(source, target, require_root=False) == "source_missing_insecure_or_invalid"
    source.chmod(0o600)
    target.chmod(0o660)
    assert module.inspect(source, target, require_root=False) == "destination_metadata_invalid"


def test_check_output_does_not_expose_key(monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "inspect", lambda: "credential_not_installed")
    assert module.main(["--check"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["credential_ready"] is False
    assert result["state"] == "credential_not_installed"
    assert "METRICS_SCRAPE_KEY=" not in json.dumps(result)


def test_install_requires_root_and_explicit_acknowledgement(monkeypatch) -> None:
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    with pytest.raises(SystemExit):
        module.main(["--apply", "--acknowledge", module.ACK])
    with pytest.raises(SystemExit):
        module.main(["--apply"])


def test_prometheus_job_has_readonly_secret_mapping() -> None:
    config = (ROOT / "apps/prometheus/prometheus.yml").read_text()
    compose = (ROOT / "apps/prometheus/compose.yml").read_text()
    job = config.split("  - job_name: fastapi_sample\n", 1)[1].split("  - job_name:", 1)[0]
    assert "authorization:" in job
    assert "type: Bearer" in job
    assert "credentials_file: /run/secrets/fastapi-sample-metrics.key" in job
    assert "source: /mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key" in compose
    assert "target: /run/secrets/fastapi-sample-metrics.key" in compose
    assert "read_only: true" in compose
    assert "create_host_path: false" in compose
    assert "METRICS_SCRAPE_KEY" not in compose
