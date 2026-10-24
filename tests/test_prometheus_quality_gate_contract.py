"""Contracts for Prometheus config validation and read-only runtime diagnostics."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_promtool_gate_validates_runtime_paths() -> None:
    source = (ROOT / "scripts" / "prometheus" / "check-config.sh").read_text(encoding="utf-8")

    assert "docker run --rm" in source
    assert "--user 568:568" in source
    assert "prom/prometheus:${PROMETHEUS_IMG:-v3.13.2}" in source
    assert "${PROMETHEUS_DIR}:/etc/prometheus:ro" in source
    assert "check config /etc/prometheus/prometheus.yml" in source


def test_prometheus_mounts_config_directory_to_survive_atomic_git_replacement() -> None:
    compose = (ROOT / "apps" / "prometheus" / "compose.yml").read_text(encoding="utf-8")

    assert "source: .\n        target: /etc/prometheus" in compose
    assert "source: ./prometheus.yml" not in compose
    assert "source: ./rules" not in compose
    assert "old inode" in compose


def test_runtime_target_diagnostic_detects_bind_mount_drift_read_only() -> None:
    source = (ROOT / "scripts" / "truenas" / "diagnose-prometheus-targets.sh").read_text(
        encoding="utf-8"
    )

    assert "sha256sum" in source
    assert "/api/v1/targets?state=active" in source
    assert "expected-jobs.txt" in source
    assert "unhealthy-targets.tsv" in source
    assert "single-file bind mount" in source
    assert "docker restart" not in source
    assert "docker rm" not in source
    assert "app.redeploy" not in source


def test_precommit_quality_gate_runs_promtool_for_prometheus_changes() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "id: prometheus-config" in config
    assert "entry: bash scripts/prometheus/check-config.sh" in config
    assert "apps/prometheus/" in config


def test_fastapi_observability_recording_rules_match_consumer_contract() -> None:
    import yaml

    rules = yaml.safe_load(
        (ROOT / "apps" / "prometheus" / "rules" / "nabla-core.rules.yml").read_text(
            encoding="utf-8"
        )
    )
    records = {
        rule["record"]: rule["expr"]
        for group in rules["groups"]
        for rule in group["rules"]
        if "record" in rule
    }
    expected = {
        "nabla:telemetry:service_exporter_up",
        "nabla:telemetry:postgres_exporter_up",
        "nabla:telemetry:redis_exporter_up",
        "nabla:telemetry:fastapi_sample_up",
        "nabla:telemetry:pyroscope_up",
        "nabla:telemetry:alertmanager_up",
        "nabla:service:postgres_up",
        "nabla:service:redis_up",
        "nabla:core:pfsense_memory_available_ratio",
    }
    assert expected <= set(records)
    assert 'pg_up{job="postgres_exporter"}' in records["nabla:service:postgres_up"]
    assert 'redis_up{job="redis_exporter"}' in records["nabla:service:redis_up"]
    assert 'max by (job)' in records["nabla:telemetry:service_exporter_up"]


def test_akvorado_scrapes_have_bounded_exporter_recordings() -> None:
    source = (ROOT / "apps/prometheus/rules/nabla-core.rules.yml").read_text(
        encoding="utf-8"
    )
    assert 'akvorado_inlet|akvorado_outlet' in source
    config = (ROOT / "apps/prometheus/prometheus.yml").read_text(
        encoding="utf-8"
    )
    assert "job_name: akvorado_inlet" in config
    assert "job_name: akvorado_outlet" in config
    assert "31057" in config
    assert "31058" in config
