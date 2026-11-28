#!/usr/bin/env python3
"""Open WebUI tool-server rows owned by scripts/openwebui/mcp-connections.sh.

Runs inside the `openwebui` container (copied there by the shell script).
Open WebUI 0.11 reads `tool_server.connections` from its database on every
MCP call, so an update needs no restart.

  check          print the ids of the owned connections
  apply          replace the owned connections with the JSON list on stdin
  verify         MCP `initialize` against each owned connection; print id and HTTP status

Owned rows are those whose info.id starts with PREFIX; the others are kept.
Nothing secret is printed.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request

DB = "/app/backend/data/webui.db"
KEY = "tool_server.connections"
PREFIX = "litellm-"


def owned(connection: dict) -> bool:
    return str((connection.get("info") or {}).get("id", "")).startswith(PREFIX)


def merge(current: list[dict], desired: list[dict]) -> list[dict]:
    """Keep the connections this script does not own, then append the desired ones."""
    return [c for c in current if not owned(c)] + desired


def _status(connection: dict) -> str:
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "nabla-check", "version": "1"}}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **(connection.get("headers") or {})}
    request = urllib.request.Request(connection["url"], data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310  # nosec B310 -- LAN gateway URL from our own rows
            return str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except OSError as exc:
        return type(exc).__name__


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    db = sqlite3.connect(DB)
    row = db.execute("select value from config where key = ?", (KEY,)).fetchone()
    current = json.loads(row[0]) if row else []
    if mode == "check":
        print(" ".join(sorted(c["info"]["id"] for c in current if owned(c))))
    elif mode == "verify":
        for connection in (c for c in current if owned(c)):
            print(connection["info"]["id"], _status(connection))
    elif mode == "apply":
        desired = json.load(sys.stdin)
        if not desired or not all(owned(c) and c.get("type") == "mcp" for c in desired):
            print("refused: every desired row must be an owned MCP connection", file=sys.stderr)
            return 1
        value = json.dumps(merge(current, desired))
        if row:
            db.execute("update config set value = ?, updated_at = ? where key = ?", (value, int(time.time()), KEY))
        else:
            db.execute("insert into config (key, value, updated_at) values (?, ?, ?)", (KEY, value, int(time.time())))
        db.commit()
        print(f"{len(desired)} connections applied")
    else:
        print("usage: tool_servers.py check|apply|verify", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
