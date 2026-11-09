"""Behaviour of scripts/media/reconcile-media-settings.py with a fake HTTP client.

--check never writes, --apply sends only drifted keys, unknown Servarr fields
fail closed, and no credential is ever printed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "media" / "reconcile-media-settings.py"
SETTINGS = yaml.safe_load((ROOT / "config" / "media" / "settings.yml").read_text(encoding="utf-8"))
# Fixture values are generated: no credential-shaped literal in Git.
SECRETS = {
    name: f"fixture-{index}-{name.lower()}"
    for index, name in enumerate((
        "QBITTORRENT_WEBUI_PASSWORD", "PROWLARR_API_KEY", "HTTPPROXY_USER",
        "HTTPPROXY_PASSWORD", "LIDARR_API_KEY", "JELLYFIN_API_KEY",
    ))
}


def load():
    spec = importlib.util.spec_from_file_location("reconcile_media_settings", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, object]] = []

    def request(self, method, path, body=None, form=None):
        self.calls.append((method, path, body if body is not None else form))
        return self.responses.get((method, path.split("?")[0]), "")

    def writes(self):
        return [call for call in self.calls if call[0] != "GET" and not call[1].endswith("/auth/login")]


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)


def qbit_client(preferences: dict, categories: dict) -> FakeClient:
    return FakeClient({
        ("POST", "/api/v2/auth/login"): "Ok.",
        ("GET", "/api/v2/app/preferences"): preferences,
        ("GET", "/api/v2/torrents/categories"): categories,
    })


def test_qbittorrent_check_reports_without_writing() -> None:
    module = load()
    report = module.Report()
    prefs = {**SETTINGS["qbittorrent"]["preferences"], "encryption": 0, "upnp": True}
    client = qbit_client(prefs, {"movies": {"savePath": "/data/torrents/movies"}})
    module.reconcile_qbittorrent(SETTINGS["qbittorrent"], False, report, client)
    assert "qbittorrent: preference encryption" in report.drifts
    assert "qbittorrent: preference upnp" in report.drifts
    assert "qbittorrent: category tv" in report.drifts
    assert client.writes() == []


def test_qbittorrent_apply_sends_only_drifted_keys() -> None:
    module = load()
    prefs = {**SETTINGS["qbittorrent"]["preferences"], "encryption": 0}
    client = qbit_client(prefs, {name: {"savePath": path} for name, path in SETTINGS["qbittorrent"]["categories"].items()})
    module.reconcile_qbittorrent(SETTINGS["qbittorrent"], True, module.Report(), client)
    writes = client.writes()
    assert len(writes) == 1 and writes[0][1] == "/api/v2/app/setPreferences"
    assert json.loads(writes[0][2]["json"]) == {"encryption": 1}


def test_prowlarr_proxy_points_at_gluetun_and_sends_password_only_on_write() -> None:
    module = load()
    client = FakeClient({("GET", "/api/v1/config/host"): {"id": 1, "proxyEnabled": False, "bindAddress": "*"}})
    report = module.Report()
    module.reconcile_prowlarr(SETTINGS["prowlarr"], True, report, client)
    method, path, body = client.writes()[0]
    assert (method, path) == ("PUT", "/api/v1/config/host/1")
    assert body["proxyHostname"] == "gluetun" and body["proxyPort"] == 8888 and body["proxyEnabled"] is True
    assert body["proxyPassword"] == SECRETS["HTTPPROXY_PASSWORD"] and body["bindAddress"] == "*"
    printed = "\n".join(report.drifts + report.applied)
    assert not any(value in printed for value in SECRETS.values())


def test_lidarr_download_client_uses_schema_fields_and_rejects_unknown_ones() -> None:
    module = load()
    schema = [{"implementation": "QBittorrent", "fields": [
        {"name": n, "value": None} for n in ("host", "port", "useSsl", "username", "password", "musicCategory")
    ]}]
    client = FakeClient({
        ("GET", "/api/v1/rootfolder"): [{"path": "/data/library/music/"}],
        ("GET", "/api/v1/downloadclient"): [],
        ("GET", "/api/v1/downloadclient/schema"): schema,
    })
    module.reconcile_lidarr(SETTINGS["lidarr"], True, module.Report(), client)
    method, path, body = client.writes()[0]
    assert (method, path) == ("POST", "/api/v1/downloadclient")
    fields = {f["name"]: f["value"] for f in body["fields"]}
    assert fields["host"] == "gluetun" and fields["musicCategory"] == "music"
    assert body["removeCompletedDownloads"] is False
    with pytest.raises(SystemExit):
        module.with_fields({"fields": [{"name": "host"}]}, {"tvCategory": "x"})


def test_jellyfin_enables_metrics_and_creates_libraries() -> None:
    module = load()
    client = FakeClient({
        ("GET", "/System/Configuration"): {"EnableMetrics": False, "ServerName": "nabla"},
        ("GET", "/Library/VirtualFolders"): [{"Name": "Films", "Locations": ["/data/library/movies"]}],
    })
    module.reconcile_jellyfin(SETTINGS["jellyfin"], True, module.Report(), client)
    writes = client.writes()
    assert writes[0] == ("POST", "/System/Configuration", {"EnableMetrics": True, "ServerName": "nabla"})
    assert [w[1].split("?")[0] for w in writes[1:]] == ["/Library/VirtualFolders", "/Library/VirtualFolders"]


def test_settings_file_holds_no_credentials() -> None:
    text = (ROOT / "config" / "media" / "settings.yml").read_text(encoding="utf-8").lower()
    for word in ("password:", "api_key:", "apikey:", "token:"):
        assert word not in text


def test_media_opentofu_unit_keeps_secrets_out_of_code() -> None:
    module = ROOT / "terraform" / "media"
    versions = (module / "versions.tofu").read_text(encoding="utf-8")
    assert "api_key" not in versions, "provider API keys come from RADARR_API_KEY/SONARR_API_KEY/PROWLARR_API_KEY"
    variables = (module / "variables.tofu").read_text(encoding="utf-8")
    for name in ("radarr_api_key", "sonarr_api_key", "lidarr_api_key", "qbittorrent_password"):
        block = variables.split(f'variable "{name}"', 1)[1].split("\n}", 1)[0]
        assert "sensitive   = true" in block and "default" not in block, name
    unit = (ROOT / "infrastructure" / "media" / "terragrunt.hcl").read_text(encoding="utf-8")
    assert 'find_in_parent_folders("terraform/media")' in unit


@pytest.mark.skipif(__import__("shutil").which("tofu") is None, reason="OpenTofu not installed")
def test_media_opentofu_unit_offline_contract() -> None:
    import subprocess

    module = ROOT / "terraform" / "media"
    subprocess.run(["tofu", f"-chdir={module}", "init", "-backend=false", "-input=false"],
                   check=True, capture_output=True)
    fixture = "dummy"  # mocked providers never use it
    env = {**__import__("os").environ, "TF_VAR_qbittorrent_password": fixture}
    result = subprocess.run(["tofu", f"-chdir={module}", "test"], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
