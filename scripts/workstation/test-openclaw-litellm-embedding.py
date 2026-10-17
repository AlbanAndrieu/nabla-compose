#!/usr/bin/env python3
"""One-shot, loopback-only LiteLLM embedding probe; never prints credentials or vectors."""
import json
import os
from pathlib import Path
import stat
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

KEY = Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key"
URL = "http://127.0.0.1:4000/v1/embeddings"

def main():
    if KEY.is_symlink() or not KEY.is_file() or stat.S_IMODE(KEY.stat().st_mode) != 0o600:
        print("✘ virtual_key=missing_or_insecure", file=sys.stderr)
        return 2
    if os.environ.get("LITELLM_WORKSTATION_URL", "http://127.0.0.1:4000").rstrip("/") not in ("http://127.0.0.1:4000", "http://localhost:4000"):
        print("✘ endpoint=not_loopback", file=sys.stderr)
        return 2
    key = KEY.read_text(encoding="utf-8").strip()
    if not key.startswith("sk-"):
        print("✘ virtual_key=invalid_format", file=sys.stderr)
        return 2
    payload = json.dumps({"model": "embedding", "input": "OpenClaw local embedding validation."}).encode("utf-8")
    request = Request(URL, data=payload, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"
    })
    try:
        with urlopen(request, timeout=45) as response:
            body = json.load(response)
    except HTTPError as exc:
        print(f"✘ embedding_request=failed http_status={exc.code}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError, OSError):
        print("✘ embedding_request=failed transport_or_json", file=sys.stderr)
        return 1
    data = body.get("data") if isinstance(body, dict) else None
    vector = data[0].get("embedding") if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict) else None
    if not isinstance(vector, list) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vector):
        print("✘ embedding_response=invalid", file=sys.stderr)
        return 1
    print("✔ embedding_request=success provider=litellm model=embedding")
    print(f"◆ embedding_dimensions={len(vector)}")
    print("✔ dimensions=expected" if len(vector) == 768 else "✘ dimensions=mismatch")
    print("ℹ NOTE: no OpenClaw configuration or index was modified")
    return 0 if len(vector) == 768 else 1

if __name__ == "__main__":
    raise SystemExit(main())
