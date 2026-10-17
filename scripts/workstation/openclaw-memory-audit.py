#!/usr/bin/env python3
"""Read-only OpenClaw memory coverage audit; never echo provider errors or secrets."""
import json
import re
import subprocess

def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=35, check=False)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""

def agents(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("agents", "results", "statuses"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []

def scalar(obj, *names):
    if not isinstance(obj, dict):
        return None
    for name in names:
        if type(obj.get(name)) in (str, int, float, bool):
            return obj[name]
    return None

def nested_scalar(obj, names, depth=0):
    if depth > 5 or not isinstance(obj, dict):
        return None
    direct = scalar(obj, *names)
    if direct is not None:
        return direct
    for key, value in obj.items():
        if key.lower() in ("error", "errors", "credentials", "auth", "apikey", "config", "env"):
            continue
        if isinstance(value, dict):
            found = nested_scalar(value, names, depth + 1)
            if found is not None:
                return found
    return None

def text_index_counts():
    """Parse only known-safe summary lines, never raw provider errors."""
    rc, output = command("openclaw", "memory", "status")
    if rc:
        return {}
    found = {}
    current = None
    for line in output.splitlines():
        heading = re.fullmatch(r"Memory Search \((main|cron)\)", line.strip())
        if heading:
            current = heading.group(1)
            continue
        if current:
            match = re.fullmatch(r"Indexed: (\d+)/(\d+) files · (\d+) chunks", line.strip())
            if match:
                found[current] = tuple(map(int, match.groups()))
    return found

def summarize(data):
    items = agents(data)
    print(f"memory_agent_records={len(items)}")
    fallback = text_index_counts()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        raw_name = scalar(item, "agentId", "agent", "id")
        name = raw_name if raw_name in ("main", "cron") else f"record_{index}"
        files = item.get("files") if isinstance(item.get("files"), dict) else {}
        indexed = nested_scalar(item, ("indexedFiles", "filesIndexed", "indexed"))
        if indexed is None:
            indexed = scalar(files, "indexed", "indexedFiles")
        total = nested_scalar(item, ("totalFiles", "filesTotal"))
        if total is None:
            total = scalar(files, "total", "totalFiles")
        chunks = nested_scalar(item, ("chunks", "chunkCount"))
        if name in fallback:
            fallback_indexed, fallback_total, fallback_chunks = fallback[name]
            if indexed is None:
                indexed = fallback_indexed
            if total is None:
                total = fallback_total
            if chunks is None:
                chunks = fallback_chunks
        dirty = nested_scalar(item, ("dirty",))
        provider = nested_scalar(item, ("provider",))
        model = nested_scalar(item, ("model",))
        for key, value in (("indexed_files", indexed), ("total_files", total), ("chunks", chunks), ("dirty", dirty)):
            if type(value) in (int, float, bool):
                print(f"memory_{name}_{key}={str(value).lower() if isinstance(value, bool) else value}")
        if provider in ("openai", "openai-compatible", "ollama", "local", "gemini", "voyage", "mistral", "bedrock", "deepinfra", "github-copilot", "lmstudio"):
            print(f"memory_{name}_provider={provider}")
        if model in ("text-embedding-3-small", "text-embedding-3-large", "embedding", "nomic-embed-text"):
            print(f"memory_{name}_model={model}")
        if type(indexed) is int and type(total) is int and total > 0:
            print(f"memory_{name}_coverage_pct={100 * indexed / total:.1f}")
            if indexed < total:
                print(f"WARN: memory_{name}_index_incomplete")
        if dirty is True:
            print(f"WARN: memory_{name}_index_dirty")
        if indexed is None or total is None:
            print(f"WARN: memory_{name}_coverage_unresolved")
    print("NOTE: no deep probe or credential output; embedding 401 requires separate safe evidence")

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
    summarize(data)
    rc, raw = command("openclaw", "config", "schema", "--json")
    if rc == 0:
        try:
            tree = json.loads(raw)
            props = tree.get("properties", {}).get("memory", {}).get("properties", {}).get("search", {}).get("properties", {})
            print("memory_search_schema=" + ("available" if props else "unresolved"))
            if props:
                print("memory_search_supports_openai_compatible=" + str("provider" in props and "remote" in props).lower())
                for field in ("provider", "model", "fallback", "remote"):
                    print(f"memory_search_field_{field}=" + str(field in props).lower())
                remote = props.get("remote", {})
                remote_props = remote.get("properties", {}) if isinstance(remote, dict) else {}
                for field in ("baseUrl", "apiKey"):
                    print(f"memory_search_remote_{field}=" + str(field in remote_props).lower())
        except (ValueError, AttributeError):
            print("memory_search_schema=invalid_json")
    else:
        print("memory_search_schema=unavailable")
    print("NOTE: no deep probe, indexing, reset, configuration mutation or API key output")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
