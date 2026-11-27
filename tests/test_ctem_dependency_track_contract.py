"""Offline contracts for the prioritized CTEM Dependency-Track pilot."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
PG_CA = "/mnt/cpool/secrets/runtime/postgres/tls/ca.crt"


def test_dependency_track_v5_is_version_pinned_and_private() -> None:
    compose = yaml.safe_load(
        (ROOT / "apps/dependency-track/compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert set(services) == {"dependency-track-api", "dependency-track"}
    for name, source in (
        ("dependency-track-api", "apiserver"),
        ("dependency-track", "frontend"),
    ):
        service = services[name]
        # A floating tag might still point to v4; require pinned v5.
        assert f"ghcr.io/dependencytrack/{source}:5.2.0" in service["image"]
        assert ":latest" not in service["image"]
        # Deployed on 25/11/2026 (rollout-pending-apps --apply dependency-track).
        assert service["x-nabla"]["status"] == "active"
        assert service["x-nabla"]["runtime"]["provider"] == "truenas-app"
        assert all(p["host_ip"] == "172.17.0.24" for p in service["ports"])
        assert "privileged" not in service and "network_mode" not in service
        assert not any(
            key.startswith("traefik.http.routers.") for key in service.get("labels", {})
        )


def test_v5_datasource_enforces_tls_and_preserves_private_secret() -> None:
    source = yaml.safe_load(
        (ROOT / "apps/dependency-track/compose.yml").read_text(encoding="utf-8")
    )["services"]["dependency-track-api"]
    env = source["environment"]
    assert env["DT_DATASOURCE_USERNAME"] == "dependencytrack"
    assert env["DT_DATASOURCE_URL"].startswith("jdbc:postgresql://")
    assert "sslmode=verify-full" in env["DT_DATASOURCE_URL"]
    assert "sslrootcert=/etc/nabla/pki/postgres-ca.crt" in env["DT_DATASOURCE_URL"]
    assert f"{PG_CA}:/etc/nabla/pki/postgres-ca.crt:ro" in source["volumes"]
    assert source["env_file"] == [
        "/mnt/cpool/secrets/runtime/dependency-track/.env.secrets"
    ]
    assert "DT_DATASOURCE_PASSWORD" not in env
    assert all(not key.startswith("ALPINE_DATABASE_") for key in env)
    assert env["DT_METRICS_ENABLED"] == "true"
    assert env["DT_MANAGEMENT_PORT"] == "9000"
    # The API port is for clients; the management port must never be
    # published on TrueNAS. Prometheus joins the same private bridge.
    assert all(port["target"] != 9000 for port in source["ports"])
    prom = yaml.safe_load(
        (ROOT / "apps/prometheus/prometheus.yml").read_text(encoding="utf-8")
    )
    job = next(j for j in prom["scrape_configs"] if j["job_name"] == "dependency_track")
    assert job["metrics_path"] == "/metrics"
    assert job["static_configs"][0]["targets"] == ["dependency-track-api:9000"]
    assert "intranet" in source["networks"]

    manifest = json.loads(
        (ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8")
    )
    entry = next(
        item for item in manifest["items"] if item["app"] == "dependency-track"
    )
    fields = {item["env"]: item for item in entry["secrets"]}
    assert fields["DT_DATASOURCE_PASSWORD"]["field"] == "ALPINE_DATABASE_PASSWORD"
    assert fields["DT_DATASOURCE_PASSWORD"]["critical"] is True
    bootstrap = (
        ROOT / "scripts/truenas/bootstrap-app-postgres.sh"
    ).read_text(encoding="utf-8")
    assert re.search(
        r'dependency-track\)\s+SECRET_KEY="DT_DATASOURCE_PASSWORD"',
        bootstrap,
    )
