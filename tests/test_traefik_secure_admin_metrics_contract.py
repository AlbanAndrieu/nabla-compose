"""Private Traefik admin endpoint, separate LAN Prometheus scrape and safe WAF."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRAEFIK = ROOT / "apps/traefik/compose.yml"
PROM = ROOT / "apps/prometheus/prometheus.yml"
AUTH = ROOT / "apps/traefik/dynamic/admin-auth.yml"


def test_admin_no_insecure_api_or_host_8080_and_private_authenticated_router():
    service = yaml.safe_load(TRAEFIK.read_text(encoding="utf-8"))["services"]["traefik"]
    cmd = service["command"]
    labels = {k: v for k, v in (label.split("=", 1) for label in service["labels"] if "=" in label)}
    assert "--api.dashboard=true" in cmd
    assert "--api.insecure=false" in cmd
    assert "--api.insecure=true" not in cmd
    assert all(p["target"] != 8080 for p in service["ports"])
    assert labels["traefik.http.routers.traefik.service"] == "api@internal"
    assert "traefik.int.albandrieu.com" in labels["traefik.http.routers.traefik.rule"]
    assert labels["traefik.http.routers.traefik.middlewares"] == "traefik-admin-auth@file"
    assert "basicauth.users=" not in TRAEFIK.read_text(encoding="utf-8")
    auth = yaml.safe_load(AUTH.read_text(encoding="utf-8"))
    users = auth["http"]["middlewares"]["traefik-admin-auth"]["basicAuth"]["users"]
    assert users == ['{{ env "TRAEFIK_DASHBOARD_BASIC_AUTH" }}']
    assert auth["http"]["middlewares"]["traefik-admin-auth"]["basicAuth"]["removeHeader"] is True
    assert "--log.level=DEBUG" not in cmd


def test_prometheus_uses_private_8082_not_admin_api():
    service = yaml.safe_load(TRAEFIK.read_text(encoding="utf-8"))["services"]["traefik"]
    assert "--entrypoints.metrics.address=:8082" in service["command"]
    assert "--metrics.prometheus.entrypoint=metrics" in service["command"]
    published = next(p for p in service["ports"] if p["name"] == "metrics")
    assert published["target"] == 8082
    assert published["published"] == "8082"
    assert published["host_ip"] == "172.17.0.24"
    config = yaml.safe_load(PROM.read_text(encoding="utf-8"))
    job = next(j for j in config["scrape_configs"] if j["job_name"] == "traefik")
    targets = [target for t in job["static_configs"] for target in t["targets"]]
    assert targets == ["172.17.0.24:8082"]
