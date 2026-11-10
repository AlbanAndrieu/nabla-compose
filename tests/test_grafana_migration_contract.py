"""Contract coverage for the Compose Grafana that took over the native data."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "grafana" / "compose.yml"


def test_compose_grafana_reuses_native_data_and_port() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert '"${GRAFANA_PORT:-30037}:3000"' in compose
    assert "/mnt/cpool/grafana/data:/var/lib/grafana" in compose
    assert 'user: "${GRAFANA_UID:-568}:${GRAFANA_GID:-568}"' in compose
