#!/usr/bin/env python3
"""Read-only authenticated LiteLLM embedding model catalog audit (no secret output)."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODELS = ("text-embedding-3-large", "text-embedding-ada-002", "embedding", "text-embedding-3-small")
KEY_FILES = {
    "local": "openclaw-embeddings.key",
    "large": "openclaw-embeddings-large.key",
    "ada": "openclaw-embeddings-ada.key",
    "small": "openclaw-embeddings-small.key",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth", choices=("master", "local", "large", "ada", "small"), default="master")
    args = parser.parse_args()
    base = os.environ.get("LITELLM_WORKSTATION_URL", "http://127.0.0.1:4000").rstrip("/")
    if base not in ("http://127.0.0.1:4000", "http://localhost:4000", "http://[::1]:4000"):
        print("ERROR: only workstation loopback LiteLLM is allowed", file=sys.stderr)
        return 2
    if args.auth == "master":
        key = os.environ.get("LITELLM_MASTER_KEY", "")
    else:
        path = Path.home() / ".local/share/nabla-compose" / KEY_FILES[args.auth]
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            print("ERROR: scoped key file missing or insecure", file=sys.stderr)
            return 2
        key = path.read_text(encoding="utf-8").strip()
    if not key:
        print("ERROR: selected credential missing", file=sys.stderr)
        return 2
    request = Request(base + "/v1/models", headers={"Authorization": "Bearer " + key})
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
    except HTTPError as exc:
        print(f"ERROR: catalog_http_status={exc.code}", file=sys.stderr)
        return 1
    except (URLError, OSError, TimeoutError, ValueError):
        print("ERROR: catalog_transport_or_json_failure", file=sys.stderr)
        return 1
    data = result.get("data", []) if isinstance(result, dict) else []
    visible = {item.get("id") for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)}
    for model in MODELS:
        print(f"{model}: {'visible' if model in visible else 'not_visible'}")
    print("NOTE: catalog visibility does not prove upstream credentials or successful embedding requests")
    print("NOTE: no model call, index mutation, or credential output")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
