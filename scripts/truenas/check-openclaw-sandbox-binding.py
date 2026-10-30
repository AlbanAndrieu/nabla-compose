#!/usr/bin/env python3
"""Read-only TrueNAS preflight for relocating the legacy OpenClaw sandbox.

Never prints app configuration or runs app.update/redeploy. A partial scan is
NOT proof that no app references the old include path.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

OLD_INCLUDE = "/mnt/cpool/compose/nabla-compose/apps/openclaw/compose.yml"
OLD_SUFFIX = "/apps/openclaw/compose.yml"
APPS = ("openclaw", "openclaw-sandbox")
MAX_BYTES = 2_000_000


def query(args):
    try:
        run = subprocess.run(args, capture_output=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0 or not (0 < len(run.stdout) <= MAX_BYTES):
        return None
    try:
        return json.loads(run.stdout)
    except (ValueError, UnicodeError):
        return None


def references_old_path(config):
    if not isinstance(config, dict):
        return "unverified_config_shape"
    values = [config]
    for key in ("custom_compose_config", "values"):
        if isinstance(config.get(key), dict):
            values.append(config[key])
    seen_field = False
    for value in values:
        include = value.get("include")
        if include is not None:
            seen_field = True
            if isinstance(include, str):
                include = [include]
            if not isinstance(include, list):
                return "unverified_include_shape"
            for item in include:
                if not isinstance(item, str):
                    return "unverified_include_shape"
                if item == OLD_INCLUDE or item.endswith(OLD_SUFFIX):
                    return "old_path_referenced"
        for key in ("custom_compose_config_string",):
            raw = value.get(key)
            if isinstance(raw, str) and raw:
                seen_field = True
                if OLD_INCLUDE in raw or OLD_SUFFIX in raw:
                    return "old_path_referenced"
    return "old_path_not_observed_in_this_config" if seen_field else "unverified_config_shape"


def audit(use_sudo=False):
    prefix = ["sudo", "-n"] if use_sudo else []
    version = query(prefix + ["midclt", "call", "system.version"])
    if not isinstance(version, str) or not version.startswith("TrueNAS-"):
        return {"host":"unverified", "sandbox_relocation":"blocked_wrong_host_or_access",
                "read_only":True}
    states = []
    for app in APPS:
        config = query(prefix + ["midclt", "call", "app.config", app])
        states.append(references_old_path(config))
    if "old_path_referenced" in states:
        verdict = "blocked_legacy_include_in_use"
    else:
        verdict = "unverified_no_global_app_reference_scan"
    return {"host":"truenas", "sandbox_relocation":verdict, "read_only":True,
            "checked_app_count":len(APPS), "app_config_readable":sum(
                x != "unverified_config_shape" for x in states),
            "old_path_reference_observed":("old_path_referenced" in states),
            "model_requests":0, "app_mutations":0}



# TrueNAS app.query enumerates every app. This secondary audit does not rely
# on guessed app names; it still never authorizes relocating the sandbox.
SAFE_APP_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
RELATIVE_LEGACY = "apps/openclaw/compose.yml"


def nested_old_reference(value, depth=0):
    """Search JSON structures for the exact legacy path, without emitting data."""
    if depth > 24:
        raise ValueError("unbounded_config_depth")
    if isinstance(value, str):
        return any(part in value for part in (OLD_INCLUDE, OLD_SUFFIX, RELATIVE_LEGACY))
    if isinstance(value, list):
        return any(nested_old_reference(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return any(nested_old_reference(k, depth + 1) or
                   nested_old_reference(v, depth + 1)
                   for k, v in value.items())
    if value is None or type(value) in (bool, int, float):
        return False
    raise ValueError("invalid_config_type")


def audit_all_apps(use_sudo=False):
    """Enumerate all currently installed TrueNAS Apps; no secrets in reports."""
    prefix = ["sudo", "-n"] if use_sudo else []
    version = query(prefix + ["midclt", "call", "system.version"])
    if not isinstance(version, str) or not version.startswith("TrueNAS-"):
        return {"host": "unverified", "sandbox_relocation":
                "blocked_wrong_host_or_access", "read_only": True,
                "model_requests": 0, "app_mutations": 0}

    records = query(prefix + ["midclt", "call", "app.query"])
    if not isinstance(records, list) or not 0 < len(records) <= 256:
        return {"host": "truenas", "sandbox_relocation":
                "unverified_app_inventory", "read_only": True,
                "app_mutations": 0, "model_requests": 0}

    ids = []
    for entry in records:
        if not isinstance(entry, dict):
            break
        app = entry.get("id")
        if not isinstance(app, str) or not SAFE_APP_ID.fullmatch(app):
            break
        ids.append(app)
    if len(ids) != len(records) or len(set(ids)) != len(ids):
        return {"host": "truenas", "sandbox_relocation":
                "unverified_app_inventory", "read_only": True,
                "app_mutations": 0, "model_requests": 0}

    checked = 0
    incomplete = 0
    observed = False
    for app in ids:
        config = query(prefix + ["midclt", "call", "app.config", app])
        if not isinstance(config, dict):
            incomplete += 1
            continue
        try:
            observed |= nested_old_reference(config)
            checked += 1
        except (ValueError, RecursionError):
            incomplete += 1
    verdict = ("blocked_legacy_include_in_use" if observed else
               "unverified_incomplete_app_scan" if incomplete else
               "manual_review_no_app_reference_observed")
    return {"host": "truenas", "sandbox_relocation": verdict,
            "read_only": True, "app_inventory_count": len(ids),
            "app_configs_checked": checked,
            "app_configs_unverified": incomplete,
            "old_path_reference_observed": observed,
            "scan_scope": "truenas_app_configs_only",
            "model_requests": 0, "app_mutations": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noninteractive-sudo", action="store_true",
                        help="Opt in to existing sudo -n rights; never prompts")
    parser.add_argument("--all-apps", action="store_true",
                        help="Enumerate and inspect every TrueNAS app configuration")
    args = parser.parse_args(argv)
    result = audit_all_apps(args.noninteractive_sudo) if args.all_apps else audit(args.noninteractive_sudo)
    print(json.dumps(result, sort_keys=True))
    return 2  # Always fail closed pending full app-reference scan & review.


if __name__ == "__main__":
    raise SystemExit(main())
