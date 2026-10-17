#!/usr/bin/env python3
"""Read-only OpenClaw LiteLLM memory configuration readiness checks.

Never prints key values, current OpenClaw config, or indexed document content.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

KEY = Path.home() / ".local/share/nabla-compose/openclaw-embeddings.key"
URL = "http://127.0.0.1:4000/v1"


def schema():
    process = subprocess.run(
        ["openclaw", "config", "schema", "--json"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if process.returncode:
        raise RuntimeError("OpenClaw schema command failed")
    return json.loads(process.stdout)


def check():
    root = schema().get("properties", {})
    properties = (
        root.get("memory", {})
        .get("properties", {}).get("search", {}).get("properties", {})
    )
    remote = properties.get("remote", {}).get("properties", {})
    provider_description = properties.get("provider", {}).get("description", "")
    sources = properties.get("sources", {}).get("items", {}).get("anyOf", [])
    secret_variants = remote.get("apiKey", {}).get("anyOf", [])
    file_secret = any(
        choice.get("properties", {}).get("source", {}).get("const") == "file"
        and {"source", "provider", "id"}.issubset(choice.get("required", []))
        for variant in secret_variants
        for choice in variant.get("oneOf", [])
    )
    providers = root.get("secrets", {}).get("properties", {}).get("providers", {})
    provider_variants = providers.get("additionalProperties", {}).get("anyOf", [])
    single_value_file_provider = any(
        variant.get("properties", {}).get("source", {}).get("const") == "file"
        and {"source", "path"}.issubset(variant.get("required", []))
        and any(mode.get("const") == "singleValue" for mode in variant.get("properties", {}).get("mode", {}).get("anyOf", []))
        for variant in provider_variants
    )
    print("file_secret_provider_schema=" + ("compatible" if single_value_file_provider else "incompatible"))
    required = (
        single_value_file_provider
        and "openai-compatible" in provider_description
        and {"model", "sources", "extraPaths"}.issubset(properties)
        and {"baseUrl", "apiKey", "batch"}.issubset(remote)
        and any(item.get("const") == "memory" for item in sources)
        and file_secret
    )
    print("memory_search_schema=" + ("compatible" if required else "incompatible"))
    try:
        metadata = KEY.lstat()
        key_ok = stat.S_ISREG(metadata.st_mode) and metadata.st_mode & 0o077 == 0
    except OSError:
        key_ok = False
    print("virtual_key_file=" + ("private" if key_ok else "missing_or_insecure"))
    print("target_provider=openai-compatible")
    print("target_model=embedding")
    print("target_endpoint=loopback")
    print("source_reindex_guard=pending")
    print("file_secret_resolution=unverified")
    print("configuration_changed=false")
    return 0 if required and key_ok else 2


def audit():
    """Run the built-in read-only audit without displaying its potentially sensitive findings."""
    process = subprocess.run(
        ["openclaw", "secrets", "audit", "--json"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    try:
        data = json.loads(process.stdout)
    except ValueError:
        print("secret_audit=unavailable")
        return 2
    if not isinstance(data, (dict, list)):
        print("secret_audit=unexpected_format")
        return 2
    print("secret_audit=completed" if process.returncode == 0 else "secret_audit=findings_or_error")
    print("secret_audit_raw_output=suppressed")
    print("file_secret_resolution=unverified")
    print("configuration_changed=false")
    return 0 if process.returncode == 0 else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--audit", action="store_true", help="Read-only secrets audit; suppress sensitive findings")
    args = parser.parse_args()
    try:
        return audit() if args.audit else check()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print("ERROR: cannot verify schema; no configuration changed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
