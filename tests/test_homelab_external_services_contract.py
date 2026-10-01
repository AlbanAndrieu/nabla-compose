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


def test_operational_catalog_uses_canonical_probe_targets() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    services = {item["name"]: item for item in payload["services"]}

    assert "Prometheus - albandrieu" not in services

    prometheus = services["Prometheus"]
    assert prometheus["id"] == "prometheus"
    assert prometheus["internalHost"] == "172.17.0.24"
    assert prometheus["internalPort"] == 9090
    assert prometheus["internalPath"] == "/-/ready"
    assert prometheus["healthPath"] == "/-/ready"

    reactive = services["Reactive Resume"]
    assert reactive["id"] == "reactive-resume"
    assert reactive["healthPath"] == "/api/health"

    traefik = services["Traefik"]
    assert traefik["id"] == "traefik"
    assert traefik["internalHost"] == "172.17.0.24"
    assert traefik["internalPort"] == 443
    assert traefik["external"] is False
    assert traefik["endpointEnabled"] is False


def test_active_operator_truenas_services_are_projected() -> None:
    generated = json.loads(
        (ROOT / "catalog" / "services.json").read_text(encoding="utf-8")
    )
    legacy = json.loads(CATALOG.read_text(encoding="utf-8"))

    projected_ids = {item.get("id") for item in legacy["services"]}
    required_ids = {
        item["id"]
        for item in generated["services"]
        if item.get("runtime", {}).get("provider") == "truenas-app"
        and item.get("status", "active") not in {"planned", "disabled"}
        and item.get("presentationRole") in {"service", "core"}
    }

    missing = required_ids - projected_ids
    assert not missing, (
        "active operator-visible TrueNAS services missing from "
        f"homelab-services.json: {sorted(missing)}"
    )
