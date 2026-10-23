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



def audit_v2_summary(data):
    """Parse documented OpenClaw audit schema; never expose finding details."""
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    status = data.get("status")
    if not isinstance(summary, dict) or status not in ("clean", "findings", "unresolved"):
        return None
    mapping = {
        "plaintextCount": "plaintext",
        "unresolvedRefCount": "unresolved",
        "shadowedRefCount": "shadowed",
        "storeResidueCount": "store_residue",
        "legacyResidueCount": "legacy_residue",
    }
    counts = {}
    for original, safe in mapping.items():
        value = summary.get(original)
        if type(value) is not int or value < 0:
            return None
        counts[safe] = value
    resolution = data.get("resolution")
    if not isinstance(resolution, dict):
        return None
    if type(resolution.get("resolvabilityComplete")) is not bool:
        return None
    return {"status": status, "categories": counts,
            "complete": resolution["resolvabilityComplete"]}



# OpenClaw v2026.9.5 src/secrets/audit.ts emits stable, non-sensitive codes.
# No arbitrary paths, provider names, profile IDs or jsonPath values are printed.
AUDIT_CODE_TO_SUMMARY = {
    "PLAINTEXT_FOUND": "plaintext",
    "REF_UNRESOLVED": "unresolved",
    "REF_SHADOWED": "shadowed",
    "STORE_PLAINTEXT_RESIDUE": "store_residue",
    "LEGACY_RESIDUE": "legacy_residue",
}
PLAINTEXT_LOCATIONS = (
    "config", "dotenv", "auth_store", "generated_models", "unknown",
)
LEGACY_LOCATIONS = ("oauth_profile", "legacy_file", "unknown")


def audit_location_breakdown(data, v2):
    """Classify aggregate locations only, with summary consistency gate.

    v2026.9.5 audit findings contain code/file/jsonPath/message and optional
    provider/profileId. NEVER return or display those fields.
    """
    if not isinstance(data, dict) or not isinstance(v2, dict):
        return None
    findings = data.get("findings")
    if not isinstance(findings, list) or len(findings) > 10000:
        return None
    counts = {key: 0 for key in PLAINTEXT_LOCATIONS}
    legacy = {key: 0 for key in LEGACY_LOCATIONS}
    codes = {code: 0 for code in AUDIT_CODE_TO_SUMMARY}
    for item in findings:
        if not isinstance(item, dict):
            return None
        code = item.get("code")
        if not isinstance(code, str) or code not in codes:
            return None
        codes[code] += 1
        if code == "PLAINTEXT_FOUND":
            file_name = item.get("file")
            if not isinstance(file_name, str):
                category = "unknown"
            else:
                base = file_name.replace("\\", "/").rsplit("/", 1)[-1]
                if base == "openclaw.json":
                    category = "config"
                elif base == ".env":
                    category = "dotenv"
                elif base == "models.json":
                    category = "generated_models"
                elif base.endswith((".sqlite", ".sqlite3", ".db")):
                    category = "auth_store"
                else:
                    category = "unknown"
            counts[category] += 1
        elif code == "LEGACY_RESIDUE":
            field = item.get("jsonPath")
            if not isinstance(field, str):
                category = "unknown"
            elif field.startswith("profiles."):
                category = "oauth_profile"
            else:
                category = "legacy_file"
            legacy[category] += 1
    counts_match = all(
        codes[code] == v2["categories"][key]
        for code, key in AUDIT_CODE_TO_SUMMARY.items()
    )
    return {"plaintext": counts, "legacy": legacy, "counts_match": counts_match}


def print_audit_location_breakdown(data, v2):
    """Emit only fixed classification labels, integer counts and gates."""
    result = audit_location_breakdown(data, v2)
    if result is None:
        print("secret_audit_location_breakdown=unavailable")
        return False
    print("secret_audit_location_breakdown=" +
          ("complete" if result["counts_match"] else "inconsistent"))
    for key in PLAINTEXT_LOCATIONS:
        print(f"secret_audit_plaintext_location_{key}={result['plaintext'][key]}")
    for key in LEGACY_LOCATIONS:
        print(f"secret_audit_legacy_location_{key}={result['legacy'][key]}")
    print("secret_audit_location_counts_match=" + str(result["counts_match"]).lower())
    print("secret_audit_sensitive_fields_exposed=false")
    return result["counts_match"]


OWNER_CATEGORIES = ("main", "cron", "other_or_shared")


def fixed_agent_owner(file_name):
    """Recognize only known, canonical agent directories; print no paths."""
    if not isinstance(file_name, str):
        return "other_or_shared"
    fields = file_name.replace("\\", "/").split("/")
    if (len(fields) >= 4 and fields[-4] == "agents"
            and fields[-3] in ("main", "cron") and fields[-2] == "agent"):
        return fields[-3]
    return "other_or_shared"


def audit_owner_breakdown(data, v2):
    """Aggregate fixed-bucket ownership, cross-checking the audited totals."""
    primary = audit_location_breakdown(data, v2)
    if primary is None or not primary["counts_match"]:
        return None
    buckets = {
        kind: {owner: 0 for owner in OWNER_CATEGORIES}
        for kind in ("auth_store", "generated_models", "legacy_file")
    }
    for item in data["findings"]:
        code = item["code"]
        file_name = item.get("file")
        base = (file_name.replace("\\", "/").rsplit("/", 1)[-1]
                if isinstance(file_name, str) else "")
        if code == "PLAINTEXT_FOUND" and base.endswith((".sqlite", ".sqlite3", ".db")):
            kind = "auth_store"
        elif code == "PLAINTEXT_FOUND" and base == "models.json":
            kind = "generated_models"
        elif (code == "LEGACY_RESIDUE" and isinstance(item.get("jsonPath"), str)
              and not item["jsonPath"].startswith("profiles.")):
            kind = "legacy_file"
        else:
            kind = None
        if kind is not None:
            buckets[kind][fixed_agent_owner(file_name)] += 1
    if (sum(buckets["auth_store"].values()) != primary["plaintext"]["auth_store"]
            or sum(buckets["generated_models"].values())
            != primary["plaintext"]["generated_models"]
            or sum(buckets["legacy_file"].values()) != primary["legacy"]["legacy_file"]):
        return None
    return buckets


def print_audit_owner_breakdown(data, v2):
    """Emit only fixed owner/source labels and non-sensitive integer counts."""
    buckets = audit_owner_breakdown(data, v2)
    if buckets is None:
        print("secret_audit_owner_breakdown=unavailable")
        return False
    print("secret_audit_owner_breakdown=complete")
    for kind in ("auth_store", "generated_models", "legacy_file"):
        for owner in OWNER_CATEGORIES:
            print(f"secret_audit_{kind}_owner_{owner}={buckets[kind][owner]}")
    print("secret_audit_owner_counts_match=true")
    return True



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



def audit_structure(data):
    """Describe shape without exposing any JSON keys, field values, or array entries."""
    if not isinstance(data, dict):
        return "not_object"
    signatures = []
    for value in data.values():
        if isinstance(value, dict):
            counts = {"array": 0, "object": 0, "scalar": 0}
            for child in value.values():
                if isinstance(child, list):
                    counts["array"] += 1
                elif isinstance(child, dict):
                    counts["object"] += 1
                else:
                    counts["scalar"] += 1
            signatures.append("object(%d,%d,%d)" % (
                counts["array"], counts["object"], counts["scalar"]))
        elif isinstance(value, list):
            types = {"object": 0, "array": 0, "scalar": 0}
            for child in value:
                if isinstance(child, dict):
                    types["object"] += 1
                elif isinstance(child, list):
                    types["array"] += 1
                else:
                    types["scalar"] += 1
            signatures.append("array(%d,%d,%d)" % (
                types["object"], types["array"], types["scalar"]))
        else:
            signatures.append("scalar")
    return ";".join(sorted(signatures))


def audit(include_locations=False):
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
    v2 = audit_v2_summary(data)
    summary = audit_summary(data) if v2 is None else {"schema": "openclaw_v2", "categories": v2["categories"], "unclassified": False}
    print("secret_audit_category_schema=" + summary["schema"])
    if v2 is not None:
        print("secret_audit_reported_status=" + v2["status"])
        print("secret_audit_resolvability_complete=" + str(v2["complete"]).lower())
    print("secret_audit_top_level_shape=" + audit_shape(data))
    print("secret_audit_nested_shape=" + audit_structure(data))
    for category, count in summary["categories"].items():
        print("secret_audit_" + category + "_count=" + str(count))
    print("secret_audit_unclassified=" + str(summary["unclassified"]).lower())
    location_ok = print_audit_location_breakdown(data, v2) if include_locations else True
    owner_ok = print_audit_owner_breakdown(data, v2) if include_locations else True
    clean = (v2 is not None and process.returncode == 0 and v2["status"] == "clean"
             and v2["complete"] and all(value == 0 for value in v2["categories"].values())
             and location_ok and owner_ok)
    print("secret_audit=" + ("clean" if clean else "findings_or_error"))
    print("secret_audit_raw_output=suppressed")
    print("secret_audit_strict_check=true")
    print("file_secret_resolution=unverified")
    print("configuration_changed=false")
    return 0 if clean else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--audit", action="store_true", help="Read-only secrets audit; suppress sensitive findings")
    modes.add_argument("--audit-locations", action="store_true",
                       help="Audit aggregate finding locations only; never print file paths")
    args = parser.parse_args()
    try:
        return audit(include_locations=args.audit_locations) if (args.audit or args.audit_locations) else check()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print("ERROR: cannot verify schema; no configuration changed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
