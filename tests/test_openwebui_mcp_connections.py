"""Open WebUI MCP connections: the script replaces only the rows it owns."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "openwebui" / "tool_servers.py"
_SPEC = importlib.util.spec_from_file_location("tool_servers", _PATH)
tool_servers = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool_servers)


def test_merge_keeps_foreign_rows_and_replaces_owned_ones() -> None:
    manual = {"type": "openapi", "info": {"id": "owner-tool"}}
    stale = {"type": "mcp", "info": {"id": "litellm-retired"}}
    fresh = {"type": "mcp", "info": {"id": "litellm-gatus"}}

    assert tool_servers.merge([manual, stale], [fresh]) == [manual, fresh]


def test_rows_without_info_are_never_owned() -> None:
    assert not tool_servers.owned({"type": "mcp"})
    assert not tool_servers.owned({"info": None})
