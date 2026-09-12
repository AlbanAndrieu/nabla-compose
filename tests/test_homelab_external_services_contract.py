import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "homelab-services.json"
OVERRIDES = ROOT / "catalog" / "homelab-exposure-overrides.json"

EXPECTED_EXTERNAL = {
    "AdGuard Home",
    "Prometheus",
    "Grafana",
    "Gatus",
    "Uptime Kuma",
    "Affine",
    "FreshRSS",
    "Clickhouse",
    "Joplin",
}


def test_selected_homelab_services_are_external() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    services = {item["name"]: item for item in payload["services"]}

    missing = EXPECTED_EXTERNAL - services.keys()
    assert not missing, f"missing homelab catalog services: {sorted(missing)}"

    disabled = {
        name for name in EXPECTED_EXTERNAL if services[name].get("external") is not True
    }
    assert not disabled, f"services must have external=true: {sorted(disabled)}"

    assert services["Joplin"]["id"] == "joplin"
    assert services["Joplin"]["internalHost"] == "172.17.0.24"
    assert services["Joplin"]["internalPort"] == 22300
    assert services["Joplin"]["tunnelUrl"] == "https://joplin.int.albandrieu.com"


def test_exposure_overrides_do_not_disable_selected_external_services() -> None:
    payload = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    overrides = {item["name"]: item for item in payload["services"]}

    disabled = {
        name
        for name in EXPECTED_EXTERNAL
        if name in overrides and overrides[name].get("external") is False
    }
    assert not disabled, f"external services disabled by exposure override: {sorted(disabled)}"
