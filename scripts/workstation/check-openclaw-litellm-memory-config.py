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
        key_ok = stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.geteuid() and metadata.st_mode & 0o077 == 0
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


def audit_summary(data):
    """Summarize only known audit category names; never echo arbitrary JSON values."""
    if not isinstance(data, dict):
        return {"schema": "unknown", "categories": {}, "unclassified": True}
    # Exact top-level category keys only; no recursive scanning of secret-bearing payloads.
    aliases = {
        "plaintext": "plaintext",
        "plaintextSecrets": "plaintext",
        "unresolved": "unresolved",
        "unresolvedRefs": "unresolved",
        "precedenceDrift": "precedence_drift",
        "precedence": "precedence_drift",
    }
    counts = {"plaintext": 0, "unresolved": 0, "precedence_drift": 0}
    matched = False
    for key, category in aliases.items():
        value = data.get(key)
        if isinstance(value, list):
            counts[category] += len(value)
            matched = True
        elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            counts[category] += value
            matched = True
    return {
        "schema": "recognized" if matched else "unknown",
        "categories": counts if matched else {},
        "unclassified": not matched,
    }


def audit_shape(data):
    """Emit only type distribution; arbitrary JSON property names and values stay private."""
    if not isinstance(data, dict):
        return "non_object"
    types = {"array": 0, "object": 0, "string": 0, "number": 0,
             "boolean": 0, "null": 0}
    for value in data.values():
        if isinstance(value, list):
            types["array"] += 1
        elif isinstance(value, dict):
            types["object"] += 1
        elif isinstance(value, bool):
            types["boolean"] += 1
        elif isinstance(value, (int, float)):
            types["number"] += 1
        elif isinstance(value, str):
            types["string"] += 1
        elif value is None:
            types["null"] += 1
    return ",".join(f"{name}:{count}" for name, count in types.items())


def audit():
    """Run the built-in read-only audit without displaying its potentially sensitive findings."""
    process = subprocess.run(
        ["openclaw", "secrets", "audit", "--check", "--json"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    print("secret_audit_exit_code=" + str(process.returncode))
    try:
        data = json.loads(process.stdout)
    except ValueError:
        print("secret_audit=invalid_json_or_command_error")
        print("secret_audit_raw_output=suppressed")
        return 2
    if not isinstance(data, (dict, list)):
        print("secret_audit=unexpected_format")
        return 2
    print("secret_audit_json_type=" + ("object" if isinstance(data, dict) else "array"))
    summary = audit_summary(data)
    print("secret_audit_category_schema=" + summary["schema"])
    print("secret_audit_top_level_shape=" + audit_shape(data))
    for category, count in summary["categories"].items():
        print("secret_audit_" + category + "_count=" + str(count))
    print("secret_audit_unclassified=" + str(summary["unclassified"]).lower())
    print("secret_audit=" + ("clean" if process.returncode == 0 and not summary["unclassified"] else "findings_or_error"))
    print("secret_audit_raw_output=suppressed")
    print("secret_audit_strict_check=true")
    print("file_secret_resolution=unverified")
    print("configuration_changed=false")
    return 0 if process.returncode == 0 and not summary["unclassified"] else 2


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
