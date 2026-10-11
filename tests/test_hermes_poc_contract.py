"""POC Hermes: offline assurance for tool, execution and telemetry boundaries."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MCP_PATH = ROOT / "scripts/hermes/readonly_mcp.py"


def load_mcp():
    spec = spec_from_file_location("readonly_mcp", MCP_PATH)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_poc_only_exposes_allowlisted_mcp_tools():
    cfg = yaml.safe_load((ROOT / "config/hermes/poc-config.yaml").read_text())
    for platform in ("telegram", "discord", "api_server", "cli"):
        assert cfg["platform_toolsets"][platform] == ["mcp-nabla_observe"]
    assert "terminal" in cfg["agent"]["disabled_toolsets"]
    assert "file" in cfg["agent"]["disabled_toolsets"]
    assert "web" in cfg["agent"]["disabled_toolsets"]
    assert "code_execution" in cfg["agent"]["disabled_toolsets"]
    assert cfg["web"]["keyless_fallback"] is False
    assert cfg["web"]["keyless_rescue"] is False
    assert cfg["model"]["provider"] == "custom"
    assert cfg["model"]["key_env"] == "HERMES_LITELLM_API_KEY"
    assert cfg["mcp_servers"]["nabla_observe"]["tools"]["resources"] is False


def test_poc_compose_has_no_host_root_or_public_ports():
    cfg = yaml.safe_load((ROOT / "poc/hermes/compose.yml").read_text())
    app = cfg["services"]["hermes"]
    assert "hermes-poc" in app["profiles"]
    assert app["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in app["security_opt"]
    assert not app.get("ports")
    assert app["environment"]["API_SERVER_ENABLED"] == "false"
    assert app["environment"]["HERMES_DASHBOARD"] == "0"
    for mount in app["volumes"]:
        assert "docker.sock" not in mount["source"]
        assert mount["source"] != "/mnt/cpool"
    assert app["env_file"][0]["required"] is True


def test_readonly_mcp_rejects_bad_service_and_raw_query(monkeypatch):
    mcp = load_mcp()
    monkeypatch.setattr(mcp, "_prom_query", lambda query: {"data": {"result": []}})
    assert mcp.scrape_status("pfsense")["status"] == "no_data"
    for bad in ("../../etc/shadow", 'gatus"} or vector(1)', "", "foobar"):
        with pytest.raises(ValueError, match="Unknown service"):
            mcp.scrape_status(bad)
    response = mcp.process({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "homelab_scrape_status",
                                       "arguments": {"service": "loki", "query": "secret"}}})
    assert response["error"]["message"] == "Observation unavailable or denied"


def test_prometheus_upstream_origin_is_not_ambient_proxy(monkeypatch):
    mcp = load_mcp()
    monkeypatch.setattr(mcp, "PROMETHEUS_URL", "http://169.254.169.254")
    with pytest.raises(ValueError, match="not allowlisted"):
        mcp._prom_query("up")
    monkeypatch.setattr(mcp, "PROMETHEUS_URL", "http://localhost:9090")
    with pytest.raises(ValueError, match="not allowlisted"):
        mcp._prom_query("up")


def test_mcp_outputs_no_labels_or_secrets(monkeypatch):
    mcp = load_mcp()
    monkeypatch.setattr(
        mcp, "_prom_query",
        lambda query: {"data": {"result": [
            {"metric": {"instance": "hidden.local:123", "secret": "DONOTLEAK"},
             "value": [1, "1"]}
        ]}},
    )
    result = mcp.process({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "homelab_scrape_status",
                                     "arguments": {"service": "loki"}}})
    assert result["result"]["content"][0]["text"] == (
        '{"service": "loki", "status": "up", "targets": 1}'
    )
    assert "DONOTLEAK" not in str(result)


def test_cost_snapshot_never_fakes_zero_for_absent_metrics(monkeypatch):
    mcp = load_mcp()
    monkeypatch.setattr(mcp, "_prom_query", lambda query: {"data": {"result": []}})
    result = mcp.process({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "hermes_litellm_cost", "arguments": {}}})
    data = __import__("json").loads(result["result"]["content"][0]["text"])
    assert data["spend_usd"] is None
    assert data["tokens"] is None
    assert data["data_status"] == "incomplete"


def test_prometheus_only_saves_hermes_key_metrics_without_pii_labels():
    prom = yaml.safe_load((ROOT / "apps/prometheus/prometheus.yml").read_text())
    job = next(c for c in prom["scrape_configs"] if c["job_name"] == "litellm_hermes")
    assert job["scrape_interval"] == "60s"
    config = job["metric_relabel_configs"]
    assert config[1]["regex"] == "hermes-poc"
    for sensitive in ("hashed_api_key", "user_email", "client_ip"):
        assert sensitive in config[2]["regex"]
