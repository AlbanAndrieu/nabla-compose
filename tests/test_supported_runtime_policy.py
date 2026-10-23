"""Read-only version policy and container-runtime detection contracts."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
mod = runpy.run_path(str(ROOT / "scripts/quality/audit-supported-runtimes.py"))
audit = mod["audit"]
status = mod["_image_status"]
normalize = mod["normalized_image"]
policy = mod["load_policy"]


def test_platform_versions_match_mise_and_talos_pins():
    cfg = policy()
    assert (ROOT / "config/talos/VERSION").read_text().strip() == "v1.14.4"
    assert (ROOT / "config/talos/KUBERNETES_VERSION").read_text().strip() == "v1.37.1"
    assert cfg["platform"]["talos"]["target"] == "v1.14.4"
    assert cfg["platform"]["kubernetes"]["target"] == "v1.37.1"
    assert cfg["languageRuntimes"]["php"]["preferred"] == "8.5.12"
    mise = (ROOT / "mise.toml").read_text()
    assert '"aqua:siderolabs/talos" = "1.14.4"' in mise
    assert "default='3.14.9'" in mise


@pytest.mark.parametrize("image,expected", [
    ("python:3.10-slim", "eol"),
    ("python:3.13.17-slim-bookworm", "security-only"),
    ("python:3.14.9-slim-bookworm", "supported"),
    ("python:3.15.1-slim", "supported"),
    ("php:8.1-apache", "eol"),
    ("php:8.2-fpm", "unverified-patch"),
    ("php:8.3-cli", "unverified-patch"),
    ("php:8.4-fpm", "unverified-patch"),
    ("php:8.4.26-fpm", "critical-patch-missing"),
    ("php:8.4.27-fpm", "supported"),
    ("php:8.5-fpm", "unverified-patch"),
    ("php:8.5.11-fpm", "critical-patch-missing"),
    ("php:8.5.12-fpm", "supported"),
    ("php:8.2.34-cli", "critical-patch-missing"),
    ("php:8.2.35-cli", "security-only"),
    ("php:8.3.35-cli", "critical-patch-missing"),
    ("php:8.3.36-cli", "security-only"),
    ("python:3.14.8-slim", "critical-patch-missing"),
    ("wordpress:latest", "unknown"),
    ("docker.io/2fauth/2fauth:8.0.1", "unknown"),
    ("docker.io/netboxcommunity/netbox:v4.7-5.1.1", "unknown"),
    ("ntninja/wordpress-postgresql:latest", "unknown"),
    ("ghcr.io/berriai/litellm:main-stable", "unknown"),
    ("redis:latest", "floating"),
    ("registry.io/mongo@sha256:" + "a" * 64, "digest-pinned"),
    ("${RUNTIME_IMAGE}", "unknown"),
])
def test_explicit_runtime_and_opaque_images_fail_safe(image, expected):
    assert status(image, policy())[0] == expected


def test_compose_default_is_not_obtained_from_private_environment():
    assert normalize("${PHP_IMAGE:-php:8.5-fpm}") == "php:8.5-fpm"
    assert normalize("${PYTHON_IMAGE}") == "${PYTHON_IMAGE}"


def test_repo_scan_reports_apps_and_nonruntime_images(tmp_path):
    (tmp_path / "apps/demo").mkdir(parents=True)
    (tmp_path / "apps/demo/compose.yml").write_text(
        "services:\n  web:\n    image: php:8.1-fpm\n"
        "  cache:\n    image: redis:latest\n"
    )
    (tmp_path / "apps/demo/Dockerfile").write_text("FROM python:3.14.9-slim-bookworm\n")
    rows = audit(tmp_path, policy())
    assert [(row["status"], row["app"]) for row in rows] == [
        ("eol", "demo"), ("floating", "demo"), ("supported", "demo"),
    ]


def test_declared_python_baseline_now_uses_python_3149():
    dockerfile = (ROOT / "apps/dsomm/baseline/Dockerfile").read_text()
    assert dockerfile.startswith("FROM python:3.14.9-slim-bookworm")
    assert "pip install" in dockerfile


def test_every_compose_image_is_visible_and_operator_never_assumes_lts():
    rows = audit(ROOT, policy())
    assert len(rows) >= 50
    assert len({row["app"] for row in rows}) >= 40
    assert not any(row["status"] == "lts" for row in rows)
    assert any(row["app"] == "wordpress" and row["status"] == "unknown"
               for row in rows)
    assert any(row["app"] == "litellm" and row["status"] == "unknown"
               for row in rows)


def test_homarr_python_reconciler_is_maintained():
    image = (ROOT / "apps/homarr/compose.yml").read_text()
    assert "docker.io/library/python:3.14.9-alpine3.24" in image
    reconciler = (ROOT / "apps/homarr/sync.py").read_text()
    assert "from urllib.request import" in reconciler


def test_vulnerable_php_is_blocking_in_strict_mode(tmp_path, capsys):
    (tmp_path / "apps/unsafe").mkdir(parents=True)
    (tmp_path / "apps/unsafe/compose.yml").write_text(
        "services:\n  unsafe:\n    image: php:8.5.11-fpm\n"
    )
    assert mod["main"](["--root", str(tmp_path), "--strict-eol"]) == 1
    output = capsys.readouterr().out
    assert "critical-patch-missing" in output
    assert "8.5.12" in output


def test_runtime_policy_is_not_a_deployment_authorization():
    cfg = json.loads((ROOT / "config/upgrades/supported-runtime-targets.json").read_text())
    assert cfg["mode"] == "reviewed_target_not_runtime_acceptance"
    assert "etcd snapshot" in " ".join(cfg["gates"])
