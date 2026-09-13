from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKER_SKILL = ROOT / ".agents" / "skills" / "docker-compose-orchestration" / "SKILL.md"
CATALOG_SKILL = ROOT / ".agents" / "skills" / "nabla-service-catalog" / "SKILL.md"
RUNTIME_LAYOUT = ROOT / "docs" / "truenas-runtime-layout.md"
SCANOPY_COMPOSE = ROOT / "apps" / "scanopy" / "compose.yml"


def test_service_creation_policy_is_reuse_first() -> None:
    docker_skill = DOCKER_SKILL.read_text(encoding="utf-8")
    catalog_skill = CATALOG_SKILL.read_text(encoding="utf-8")
    runtime_layout = RUNTIME_LAYOUT.read_text(encoding="utf-8")

    for service in ("PostgreSQL", "Redis", "ClickHouse", "InfluxDB", "OpenSearch"):
        assert service in docker_skill
        assert service in runtime_layout

    assert "Shared-service reuse gate" in docker_skill
    assert "Reuse a compatible existing shared service by default" in docker_skill
    assert "concrete, documented incompatibility" in docker_skill
    assert "Sentry's dedicated ClickHouse" in docker_skill
    assert "reuse-first" in catalog_skill
    assert "canonical shared node" in catalog_skill
    assert "Shared infrastructure is reuse-first" in runtime_layout


def test_scanopy_reuses_canonical_postgresql_node() -> None:
    compose = SCANOPY_COMPOSE.read_text(encoding="utf-8")

    assert "scanopy-postgres:" not in compose
    assert "target: postgresql" in compose
    assert "SCANOPY_DATABASE_URL" in compose
    assert "/mnt/cpool/scanopy/postgres" not in compose
