"""Contract of the scripts/mcp launchers for Homarr, Grafana, Gatus and FastAPI Sample."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "scripts/mcp"


def _servers() -> dict:
    return json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def _stdio(*args: str) -> dict:
    return {"type": "stdio", "command": "bash", "args": list(args)}


def test_mcp_json_starts_launchers_without_unset_variables():
    servers = _servers()
    assert servers["homarr"] == _stdio("scripts/mcp/http-remote.sh", "homarr", "http://172.17.0.24:30100/api/mcp/mcp")
    assert servers["fastapi-sample"] == _stdio("scripts/mcp/http-remote.sh", "fastapi-sample", "http://172.17.0.24:8091/mcp")
    assert servers["grafana"] == _stdio("scripts/mcp/grafana.sh")
    assert servers["gatus"] == _stdio("scripts/mcp/gatus.sh")


@pytest.mark.parametrize(
    ("args", "file"),
    [
        (["http-remote.sh", "homarr", "http://192.0.2.1/mcp"], "homarr.headers"),
        (["grafana.sh"], "grafana.env"),
    ],
)
@pytest.mark.parametrize("mode", [None, 0o644])
def test_launchers_refuse_a_missing_or_readable_credential_file(tmp_path, args, file, mode):
    if mode is not None:
        (tmp_path / file).write_text("ApiKey: not-a-real-key\n", encoding="utf-8")
        (tmp_path / file).chmod(mode)
    env = dict(os.environ, NABLA_MCP_KEY_DIR=str(tmp_path))
    result = subprocess.run(["bash", str(MCP / args[0]), *args[1:]], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert "not-a-real-key" not in result.stdout + result.stderr


def test_keys_never_reach_a_command_line():
    remote = (MCP / "http-remote.sh").read_text(encoding="utf-8")
    assert '--header-file "${headers}"' in remote and "--header " not in remote
    grafana = (MCP / "grafana.sh").read_text(encoding="utf-8")
    assert '--env-file "${env_file}"' in grafana
    for flag in ("--rm", "--read-only", "--cap-drop=ALL", "--disable-write", "grafana/mcp-grafana:1.2.0-alpine"):
        assert flag in grafana
    assert 'MCP_REMOTE_PACKAGE="mcp-remote@0.16.5"' in (MCP / "lib.sh").read_text(encoding="utf-8")


def test_gatus_runs_pinned_on_loopback_without_a_write_token():
    text = (MCP / "gatus.sh").read_text(encoding="utf-8")
    assert "GATUS_MCP_COMMIT=4c7ed599114d920437bd37f6590744573e361e46" in text
    assert "MCP_HOST=127.0.0.1" in text
    assert "GATUS_TOKEN" not in text.split("set -euo pipefail", 1)[1]


def test_materializer_needs_vaultwarden_and_writes_private_files(tmp_path):
    script = MCP / "materialize-keys.sh"
    env = {k: v for k, v in os.environ.items() if k != "BW_SESSION"}
    env["NABLA_MCP_KEY_DIR"] = str(tmp_path / "keys")
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1 and not (tmp_path / "keys").exists()
    text = script.read_text(encoding="utf-8")
    assert "umask 077" in text and 'chmod 600 "${tmp}"' in text
    for target in ("homarr.headers|nabla/prod/homarr|HOMARR_API_KEY", "grafana.env|nabla/prod/grafana-observability",
                   "fastapi-sample.headers|nabla/prod/fastapisample|MCP_OPS_KEY|X-MCP-Key"):
        assert target in text
