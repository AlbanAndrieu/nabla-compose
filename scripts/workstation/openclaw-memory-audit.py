#!/usr/bin/env python3
"""Read-only, redacted OpenClaw memory status and embedding configuration audit."""
import json
import re
import subprocess

def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=35, check=False)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""

def walk(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                yield k, v
            if isinstance(v, (dict, list)):
                yield from walk(v, keys)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, keys)

def main():
    rc, raw = command("openclaw", "memory", "status", "--json")
    if rc or not raw.strip():
        print("memory_status=unavailable")
        return 2
    try:
        data = json.loads(raw)
    except ValueError:
        print("memory_status=invalid_json")
        return 2
    print("memory_status=available")
    # Avoid printing raw fields: provider errors may contain partial API keys.
    for key, value in walk(data, {"provider", "model", "dirty", "indexedFiles", "totalFiles", "chunks", "vectorSearch", "embeddings"}):
        if isinstance(value, (str, int, float, bool)) and key not in ("embeddings",):
            if key in ("provider", "model") and not re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", str(value)):
                continue
            if key not in ("provider", "model") or len(str(value)) < 100:
                print(f"memory_{key}={value}")
    # Probe can contact remote provider: opt-in only, do not print raw errors.
    rc, schema = command("openclaw", "config", "schema", "--json")
    if rc == 0:
        try:
            tree = json.loads(schema)
            props = tree.get("properties", {})
            memory = props.get("memory", {})
            search = memory.get("properties", {}).get("search", {}).get("properties", {})
            print("memory_search_schema=" + ("available" if search else "unresolved"))
            if search:
                print("memory_search_schema_fields=" + ",".join(sorted(search.keys())))
        except ValueError:
            print("memory_search_schema=invalid_json")
    else:
        print("memory_search_schema=unavailable")
    print("NOTE: no deep probe, indexing, reset, configuration mutation or API key output")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
