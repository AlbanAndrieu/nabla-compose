"""Security contract of the planned *arr media stack.

Design: docs/arr-media-library-roadmap.md. The download client must have no
egress outside the Gluetun VPN namespace, DNS must stay encrypted inside the
tunnel, and no media UI may be published outside the LAN.
"""

from __future__ import annotations

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
MEDIA_APPS = (
    "media-acquisition", "prowlarr", "radarr", "sonarr", "lidarr",
    "bazarr", "recyclarr", "jellyfin", "seerr", "qbittorrent-exporter",
)
EXPORTARR = ("prowlarr", "radarr", "sonarr", "lidarr", "bazarr")
SERVARR = ("prowlarr", "radarr", "sonarr", "lidarr")
PINNED = re.compile(r"^[a-z0-9./-]+:v?\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")
LAN_IP = "172.17.0.24"


def compose(app: str) -> dict:
    return yaml.safe_load((ROOT / "apps" / app / "compose.yml").read_text(encoding="utf-8"))


def services() -> dict[str, tuple[str, dict]]:
    found: dict[str, tuple[str, dict]] = {}
    for app in MEDIA_APPS:
        for name, service in compose(app)["services"].items():
            found[name] = (app, service)
    return found


def env(service: dict) -> dict:
    raw = service.get("environment") or {}
    assert isinstance(raw, dict), "media services declare environment as a mapping"
    return {key: str(value) for key, value in raw.items()}


def test_every_media_service_is_planned_pinned_and_catalogued() -> None:
    for name, (app, service) in services().items():
        assert PINNED.match(service["image"]), (name, service["image"])
        meta = service["x-nabla"]
        assert meta["id"] == name
        expected = "observability" if name.endswith("-exporter") else "media"
        assert meta["category"] == expected, name
        assert meta["status"] == "planned", "activate only after the roadmap acceptance tests"
        assert meta["runtime"] == {"provider": "truenas-app", "containerService": name}
        labels = service["labels"]
        ref = labels["com.albandrieu.nabla.entity-ref"]
        assert ref == f"component:default/{name}"
        catalog = (ROOT / "apps" / app / "catalog-info.yaml").read_text(encoding="utf-8")
        assert f"  name: {name}\n" in catalog, (app, name)


def test_only_gluetun_holds_network_privileges() -> None:
    for name, (_, service) in services().items():
        assert not service.get("privileged"), name
        assert service.get("network_mode") != "host", name
        volumes = " ".join(str(item) for item in service.get("volumes", []))
        assert "docker.sock" not in volumes, name
        if name == "gluetun":
            assert service["cap_add"] == ["NET_ADMIN"]
            assert service["devices"] == ["/dev/net/tun:/dev/net/tun"]
        else:
            assert "cap_add" not in service, name
            assert "/dev/net/tun" not in str(service.get("devices", [])), name


def test_qbittorrent_has_no_egress_outside_the_vpn_namespace() -> None:
    stack = compose("media-acquisition")["services"]
    assert set(stack) == {"gluetun", "qbittorrent"}, "nothing else may join the VPN namespace"
    for name, (_, service) in services().items():
        if name != "qbittorrent":
            assert service.get("network_mode") is None, name
    qbit = stack["qbittorrent"]
    assert qbit["network_mode"] == "service:gluetun"
    assert "ports" not in qbit and "networks" not in qbit
    assert qbit["depends_on"]["gluetun"] == {"condition": "service_healthy", "restart": True}


def test_gluetun_keeps_dns_encrypted_inside_the_tunnel() -> None:
    gluetun = compose("media-acquisition")["services"]["gluetun"]
    values = env(gluetun)
    assert values["VPN_SERVICE_PROVIDER"] == "protonvpn"
    assert values["VPN_TYPE"] == "wireguard"
    assert values["DNS_UPSTREAM_RESOLVER_TYPE"] == "dot"
    assert "DNS_UPSTREAM_PLAIN_ADDRESSES" not in values
    assert values["PORT_FORWARD_ONLY"] == "on"
    assert values["VPN_PORT_FORWARDING"] == "on"
    assert "127.0.0.1:8080/api/v2/app/setPreferences" in values["VPN_PORT_FORWARDING_UP_COMMAND"]
    assert values["HTTPPROXY"] == "on" and values["HTTPPROXY_LOG"] == "off"
    for secret in ("WIREGUARD_PRIVATE_KEY", "HTTPPROXY_USER", "HTTPPROXY_PASSWORD"):
        assert secret not in values, "VPN and proxy credentials come only from the runtime env_file"
    assert gluetun["sysctls"]["net.ipv6.conf.all.disable_ipv6"] == 1


def test_secrets_use_the_canonical_runtime_env_files_only() -> None:
    for name, (app, service) in services().items():
        for env_file in service.get("env_file", []):
            assert env_file == f"/mnt/cpool/secrets/runtime/{app}/.env.secrets", (name, env_file)
        for key in env(service):
            assert not re.search(r"(APIKEY|API_KEY|PASSWORD|PRIVATE_KEY|TOKEN)$", key), (name, key)


def test_media_uis_are_lan_only() -> None:
    for name, (_, service) in services().items():
        for port in service.get("ports", []):
            assert port["host_ip"] == LAN_IP, name
        for key, value in (service.get("labels") or {}).items():
            if key.endswith(".rule"):
                assert re.fullmatch(r"Host\(`[a-z0-9-]+\.int\.albandrieu\.com`\)", value), (name, value)
    tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text(encoding="utf-8")
    for host in ("emby", "jellyfin", "radarr", "sonarr", "prowlarr", "lidarr", "qbittorrent", "seerr"):
        assert f'"{host}.albandrieu.com"' not in tunnel, host


def test_library_mounts_share_one_dataset_and_jellyfin_is_read_only() -> None:
    for name, (_, service) in services().items():
        media = [str(v) for v in service.get("volumes", []) if str(v).startswith("/mnt/cpool/media")]
        if name == "jellyfin":
            assert media == ["/mnt/cpool/media/library:/data/library:ro"]
        elif media:
            assert media == ["/mnt/cpool/media:/data"], (name, media)


def test_servarr_apps_enforce_forms_authentication_without_analytics() -> None:
    for app in SERVARR:
        values = env(compose(app)["services"][app])
        upper = app.upper()
        assert values[f"{upper}__AUTH__METHOD"] == "Forms"
        assert values[f"{upper}__AUTH__REQUIRED"] == "Enabled"
        assert values[f"{upper}__LOG__ANALYTICSENABLED"] == "False"


def test_recyclarr_config_reads_keys_from_the_environment() -> None:
    text = (ROOT / "apps/recyclarr/config/recyclarr.yml").read_text(encoding="utf-8")
    keys = re.findall(r"^\s*api_key:\s*(.+)$", text, re.MULTILINE)
    assert keys == ["!env_var RADARR_API_KEY", "!env_var SONARR_API_KEY"]
    assert "Put your" not in text


def test_deploy_script_refuses_native_apps_and_never_pulls() -> None:
    script = (ROOT / "scripts/truenas/deploy-media-stack.sh").read_text(encoding="utf-8")
    assert ".[0].custom_app == true" in script
    assert "READ_ONLY:" in script
    assert 'bootstrap-repository-runtime.sh --apply "${APP_ID}"' in script
    for forbidden in ("app.delete", "docker compose up", "zfs destroy", "--no-verify"):
        assert forbidden not in script, forbidden
    assert not re.search(r"^\s*docker pull", script, re.MULTILINE)
    for app in MEDIA_APPS:
        assert app in script, app


def test_every_media_container_ships_logs_and_exposes_metrics() -> None:
    for name, (_, service) in services().items():
        assert service["labels"]["com.albandrieu.nabla.logs"] == "media", name
    prometheus = yaml.safe_load((ROOT / "apps/prometheus/prometheus.yml").read_text(encoding="utf-8"))
    targets = {
        job["job_name"]: job["static_configs"][0]["targets"]
        for job in prometheus["scrape_configs"] if job.get("static_configs")
    }
    for app in EXPORTARR:
        exporter = compose(app)["services"][f"{app}-exporter"]
        assert exporter["command"] == [app]
        assert exporter["read_only"] is True and exporter["cap_drop"] == ["ALL"]
        assert "intranet" in exporter["networks"] and "ports" not in exporter
        assert targets[f"exportarr_{app}"] == [f"{app}-exporter:9707"]
    assert targets["qbittorrent"] == ["qbittorrent-exporter:8090"]
    assert targets["jellyfin"] == [f"{LAN_IP}:30013"]
    alloy = (ROOT / "apps/grafana/config/alloy.alloy").read_text(encoding="utf-8")
    assert 'values = ["com.albandrieu.nabla.logs"]' in alloy
    assert 'host = "tcp://docker-socket-proxy:2375"' in alloy
    assert "unix:///var/run/docker.sock" not in alloy
    dashboard = (ROOT / "apps/grafana/config/dashboards/media/media-stack.json").read_text(encoding="utf-8")
    assert '"uid": "nabla_media_stack"' in dashboard


def test_qbittorrent_exporter_never_sees_the_wireguard_key() -> None:
    exporter = compose("qbittorrent-exporter")["services"]["qbittorrent-exporter"]
    assert exporter["env_file"] == ["/mnt/cpool/secrets/runtime/qbittorrent-exporter/.env.secrets"]
    assert exporter.get("network_mode") is None
    assert env(exporter)["QBITTORRENT_BASE_URL"] == "http://gluetun:8080"
