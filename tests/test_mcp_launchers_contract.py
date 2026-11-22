"""Contract of the LiteLLM MCP gateway, the scripts/mcp launchers and the Grafana MCP identity."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "scripts/mcp"
GATEWAY = ROOT / "scripts/litellm/mcp-gateway.sh"
GRAFANA_IDENTITY = ROOT / "scripts/grafana/mcp-identity.sh"


def _servers() -> dict:
    return json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def _stdio(*args: str) -> dict:
    return {"type": "stdio", "command": "bash", "args": list(args)}


def _compose(app: str) -> dict:
    return yaml.safe_load((ROOT / f"apps/{app}/compose.yml").read_text(encoding="utf-8"))["services"]


def test_mcp_json_reaches_homarr_and_grafana_through_the_gateway():
    servers = _servers()
    assert servers["nabla-mcp"] == _stdio("scripts/mcp/http-remote.sh", "litellm-gateway", "http://172.17.0.24:4000/mcp/")
    assert servers["fastapi-sample"] == _stdio("scripts/mcp/http-remote.sh", "fastapi-sample", "http://172.17.0.24:8091/mcp")
    assert servers["gatus"] == _stdio("scripts/mcp/gatus.sh")
    assert "homarr" not in servers and "grafana" not in servers


def _payload(server: str, key: str) -> dict:
    """Run the gateway's payload builder alone, the upstream key in its environment only."""
    script = (
        f'source <(sed -n "/^server_payload()/,/^}}/p" {GATEWAY}); '
        f"HOMARR_TOOLS={ROOT}/scripts/litellm/homarr-readonly-tools.json HOMARR_MCP_URL=h GRAFANA_MCP_URL=g "
        f'ACCESS_GROUP=nabla-mcp; UPSTREAM_KEY="$K" server_payload {server}'
    )
    out = subprocess.run(["bash", "-c", script], env=dict(os.environ, K=key), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_gateway_registers_upstream_credentials_in_the_litellm_database_only():
    config = yaml.safe_load((ROOT / "apps/litellm/config.yaml").read_text(encoding="utf-8"))["mcp_servers"]
    assert set(config) == {"cyberbro"} and config["cyberbro"]["access_groups"] == ["nabla-mcp"]
    litellm = _compose("litellm")["litellm"]
    assert litellm["env_file"] == ["/mnt/cpool/secrets/runtime/litellm/.env.secrets"]
    assert not {"HOMARR_API_KEY", "MCP_GRAFANA_SERVER_TOKEN"} & set(litellm.get("environment", {}))

    homarr, grafana = _payload("homarr", "not-a-real-key"), _payload("grafana", "not-a-real-token")
    assert homarr["auth_type"] == "api_key" and homarr["credentials"] == {
        "auth_value": "not-a-real-key",
        "upstream_token_header": "ApiKey",
    }
    assert grafana["auth_type"] == "bearer_token" and grafana["credentials"] == {"auth_value": "not-a-real-token"}
    for server in (homarr, grafana):
        assert server["mcp_access_groups"] == ["nabla-mcp"] and server["transport"] == "http"
        assert "static_headers" not in server
    writes = ("delete", "create", "update", "save", "set", "rename", "reset", "add", "remove", "duplicate", "change")
    assert len(homarr["allowed_tools"]) == 77
    assert not [t for t in homarr["allowed_tools"] if t.split("_", 1)[-1].lower().startswith(writes)]


def test_grafana_mcp_is_its_own_read_only_authenticated_app():
    assert "mcp-grafana" not in _compose("grafana")
    sidecar = _compose("grafana-observability")["mcpgrafana"]
    assert "-disable-write" in sidecar["command"] and "streamable-http" in sidecar["command"]
    assert sidecar["read_only"] is True and sidecar["cap_drop"] == ["ALL"]
    assert sidecar["env_file"] == [
        {"path": "/mnt/cpool/secrets/runtime/grafana-observability/.env.secrets", "required": True}
    ]
    assert "@sha256:" in sidecar["image"]
    assert not any("TOKEN" in key for key in sidecar.get("environment", {}))
    deploy = (ROOT / "scripts/truenas/deploy-grafana-observability.sh").read_text(encoding="utf-8")
    assert 'unauth}" == 401' in deploy and "grep -q '^MCP_GRAFANA_SERVER_TOKEN=.'" in deploy


def test_grafana_service_account_is_code_and_its_token_stays_out_of_state():
    tofu = (ROOT / "terraform/grafana/main.tofu").read_text(encoding="utf-8")
    assert 'resource "grafana_service_account" "mcp_readonly"' in tofu and 'role        = "Viewer"' in tofu
    assert "grafana_service_account_token" not in tofu
    assert 'find_in_parent_folders("terraform/grafana")' in (ROOT / "infrastructure/grafana/terragrunt.hcl").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("script", [GATEWAY, GRAFANA_IDENTITY])
def test_vaultwarden_scripts_refuse_without_a_session(script):
    env = {k: v for k, v in os.environ.items() if k != "BW_SESSION"}
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode == 2
    assert subprocess.run(["bash", str(script), "check"], env=env, capture_output=True).returncode == 1


def test_keys_never_reach_a_command_line():
    assert "curl -sS --noproxy '*' -K -" in GRAFANA_IDENTITY.read_text(encoding="utf-8")
    gateway = GATEWAY.read_text(encoding="utf-8")
    assert "curl -sS --noproxy '*' -K <(printf 'header = \"Authorization: Bearer %s\"" in gateway
    assert "--data-binary @-" in gateway and "data=(-d" not in gateway
    # The owner shell exports LITELLM_URL for the workstation LiteLLM (same master key).
    assert "\nLITELLM_URL=http://172.17.0.24:4000\n" in gateway and "${LITELLM_URL:-" not in gateway
    assert "\nexport GRAFANA_URL=http://172.17.0.24:30037\n" in GRAFANA_IDENTITY.read_text(encoding="utf-8")
    assert 'models:["no-default-models"]' in gateway and "object_permission:{mcp_access_groups:[$g]}" in gateway
    remote = (MCP / "http-remote.sh").read_text(encoding="utf-8")
    assert '--header-file "${headers}"' in remote and "--header " not in remote
    assert 'MCP_REMOTE_PACKAGE="mcp-remote@0.16.5"' in (MCP / "lib.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", [None, 0o644])
def test_http_launcher_refuses_a_missing_or_readable_headers_file(tmp_path, mode):
    headers = tmp_path / "litellm-gateway.headers"
    if mode is not None:
        headers.write_text("x-litellm-api-key: Bearer not-a-real-key\n", encoding="utf-8")
        headers.chmod(mode)
    env = dict(os.environ, NABLA_MCP_KEY_DIR=str(tmp_path))
    result = subprocess.run(["bash", str(MCP / "http-remote.sh"), "litellm-gateway", "http://192.0.2.1/mcp/"],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert "not-a-real-key" not in result.stdout + result.stderr


def test_gatus_runs_pinned_on_loopback_without_a_write_token():
    text = (MCP / "gatus.sh").read_text(encoding="utf-8")
    assert "GATUS_MCP_COMMIT=4c7ed599114d920437bd37f6590744573e361e46" in text
    assert "MCP_HOST=127.0.0.1" in text
    assert "GATUS_TOKEN" not in text.split("set -euo pipefail", 1)[1]


def test_materializer_needs_vaultwarden(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "BW_SESSION"}
    env["NABLA_MCP_KEY_DIR"] = str(tmp_path / "keys")
    result = subprocess.run(["bash", str(MCP / "materialize-keys.sh")], env=env, capture_output=True, timeout=20)
    assert result.returncode == 1 and not (tmp_path / "keys").exists()


def test_runtime_install_over_ssh_streams_the_file_and_always_cleans_up(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts/secrets"))
    spec = importlib.util.spec_from_file_location("materialize_runtime", ROOT / "scripts/secrets/materialize_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = tmp_path / ".env.secrets"
    rendered.write_text("A=not-a-real-value\n", encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv[-1])
        if argv[-1] == "umask 077 && mktemp":
            return subprocess.CompletedProcess(argv, 0, stdout="/tmp/tmp.abc\n")
        if argv[-1].startswith("sudo"):
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, stdout="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        module.install_over_ssh("truenas", "--install", "grafana-observability", rendered, {})
    assert calls[1] == "cat > /tmp/tmp.abc"
    assert calls[2].startswith("sudo -n bash /mnt/cpool/compose/nabla-compose/scripts/truenas/install-runtime-secret.sh")
    assert calls[-1] == "rm -f /tmp/tmp.abc"
    assert not any("not-a-real-value" in c for c in calls)
