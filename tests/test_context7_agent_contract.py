from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP_CONFIGS = (ROOT / ".mcp.json", ROOT / ".cursor" / "mcp.json")
AGENTS = ROOT / "AGENTS.md"
CONTEXT7_SKILL = ROOT / ".agents" / "skills" / "context7-docs" / "SKILL.md"
LOCAL_FIRST_SKILL = ROOT / ".agents" / "skills" / "local-first-quality" / "SKILL.md"
OPENCODE = ROOT / "opencode.json"


def test_context7_mcp_is_free_anonymous_first() -> None:
    for path in MCP_CONFIGS:
        config = json.loads(path.read_text(encoding="utf-8"))
        context7 = config["mcpServers"]["context7"]

        assert context7 == {
            "type": "http",
            "url": "https://mcp.context7.com/mcp",
        }
        assert "CONTEXT7_API_KEY" not in path.read_text(encoding="utf-8")


def test_opencode_v2_context7_is_free_first_and_codemode_bounded() -> None:
    raw = OPENCODE.read_text(encoding="utf-8")
    config = json.loads(raw)

    assert "servers" in config["mcp"]
    context7 = config["mcp"]["servers"]["context7"]
    assert context7 == {
        "type": "remote",
        "url": "https://mcp.context7.com/mcp",
        "codemode": True,
    }
    assert "headers" not in context7
    assert "oauth" not in context7
    assert "CONTEXT7_API_KEY" not in raw


def test_context7_skill_keeps_external_docs_bounded() -> None:
    skill = CONTEXT7_SKILL.read_text(encoding="utf-8")

    for expected in (
        "Free-first policy",
        "anonymous/free access",
        "CTX7_TELEMETRY_DISABLED=1",
        "ctx7 library",
        "ctx7 docs",
        "CONTEXT7_API_KEY",
        "optional",
        "exact version-specific ID",
        "repository state",
        "runtime evidence",
        "official documentation/release notes",
    ):
        assert expected in skill

    assert "Never require it for normal agent operation" in skill
    assert "Do not send secrets" in skill


def test_agent_policy_routes_context7_only_for_external_docs() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    local_first = LOCAL_FIRST_SKILL.read_text(encoding="utf-8")

    assert "Context7 is documentation-only and free-first" in agents
    assert "load `context7-docs` on demand" in agents
    assert "repository/runtime evidence remains authoritative" in agents
    assert "anonymous/free access first" in local_first
    assert "repository/runtime evidence authoritative" in local_first
