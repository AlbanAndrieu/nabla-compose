"""Contract of the read-only TrueNAS MCP: launcher, TLS pin, identity script."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/mcp/truenas-readonly.sh"
PIN = ROOT / "scripts/mcp/truenas-pin-host.mjs"
IDENTITY = ROOT / "scripts/truenas/mcp-readonly-identity.sh"


def test_mcp_json_starts_the_launcher_without_inline_secrets():
    server = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["truenas-readonly"]
    assert server == {"type": "stdio", "command": "bash", "args": ["scripts/mcp/truenas-readonly.sh"]}


def test_launcher_keeps_tls_verified_and_leaves_the_repository_dotenv_alone():
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "export TRUENAS_INSECURE=false" in text
    assert "@profanter-dev/truenas-mcp@1.0.6" in text
    assert "truenas-pin-host.mjs" in text
    assert 'cd "${HERE}"' in text
    assert not (LAUNCHER.parent / ".env").exists()


@pytest.mark.parametrize("mode", [None, 0o644])
def test_launcher_refuses_a_missing_or_readable_key_file(tmp_path, mode):
    key = tmp_path / "truenas-readonly.key"
    if mode is not None:
        key.write_text("not-a-real-key\n", encoding="utf-8")
        key.chmod(mode)
    env = {k: v for k, v in os.environ.items() if k != "TRUENAS_MCP_API_KEY"}
    env["TRUENAS_MCP_KEY_FILE"] = str(key)
    result = subprocess.run(["bash", str(LAUNCHER)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert "not-a-real-key" not in result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_pin_resolves_only_the_pinned_name():
    script = (
        "import dns from 'node:dns';"
        "dns.lookup('truenas.example.test', (e, a, f) => {"
        "  dns.lookup('truenas.example.test', {all: true}, (e2, all) => {"
        "    dns.lookup('localhost', (e3, other) => console.log(JSON.stringify({a, f, all, other})));"
        "  });"
        "});"
    )
    env = dict(os.environ, NABLA_PIN_HOST="truenas.example.test", NABLA_PIN_ADDR="192.0.2.24",
               NODE_OPTIONS=f"--import=file://{PIN}")
    out = subprocess.run(["node", "--input-type=module", "-e", script], env=env, capture_output=True,
                         text=True, timeout=20, check=True)
    data = json.loads(out.stdout)
    assert data["a"] == "192.0.2.24" and data["f"] == 4
    assert data["all"] == [{"address": "192.0.2.24", "family": 4}]
    assert data["other"] != "192.0.2.24"


def test_identity_script_never_prints_the_key_and_needs_vaultwarden_first():
    text = IDENTITY.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(IDENTITY)], check=True)
    assert subprocess.run(["bash", str(IDENTITY)], capture_output=True).returncode == 2
    assert text.index('BW_SESSION:-') < text.index("api_key.create")
    assert "jq -er '.key' >\"${tmp}\"" in text
    assert "--app truenas-mcp-readonly" in text


def test_manifest_declares_the_vaultwarden_item():
    manifest = json.loads((ROOT / "config/secrets/manifest.json").read_text(encoding="utf-8"))
    (item,) = [i for i in manifest["items"] if i["app"] == "truenas-mcp-readonly"]
    assert item["item"] == "nabla/prod/truenas-mcp-readonly"
    assert [s["env"] for s in item["secrets"]] == ["TRUENAS_MCP_API_KEY"]
