"""Contract coverage for the native TrueNAS Grafana -> Compose migration."""

from pathlib import Path
import stat


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "scripts" / "truenas" / "diagnose-grafana-migration.sh"
ROADMAP = ROOT / "docs" / "roadmap.md"
COMPOSE = ROOT / "apps" / "grafana" / "compose.yml"


def test_grafana_migration_preflight_is_read_only_and_executable() -> None:
    source = DIAGNOSTIC.read_text(encoding="utf-8")
    mode = DIAGNOSTIC.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "/mnt/cpool/grafana/data" in source
    assert "grafana.db" in source
    assert "mode=ro" in source
    assert '"dashboard"' in source
    assert '"data_source"' in source
    assert "30037" in source

    # The preflight inventories identities/endpoints only; it must never dump
    # datasource credentials or mutate the native data before migration.
    assert "secure_json_data" not in source
    assert "basic_auth_password" not in source
    assert "password" not in source.lower()
    for destructive in ("rm -rf", "docker rm", "app.delete", "zfs destroy"):
        assert destructive not in source


def test_compose_grafana_reuses_native_data_and_port() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert '"${GRAFANA_PORT:-30037}:3000"' in compose
    assert "/mnt/cpool/grafana/data:/var/lib/grafana" in compose
    assert 'user: "${GRAFANA_UID:-568}:${GRAFANA_GID:-568}"' in compose


def test_roadmap_sequences_grafana_before_full_observability_stack() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert "diagnose-grafana-migration.sh --check" in roadmap
    assert "Grafana native → Compose migration" in roadmap
    assert "PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch" in roadmap
    assert "Sybase" in roadmap
    assert "excluded" in roadmap

    migration = roadmap.index("Grafana native → Compose migration")
    full_stack = roadmap.index("Mimir / Loki / Tempo / Alloy", migration)
    assert migration < full_stack
