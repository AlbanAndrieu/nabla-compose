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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noninteractive-sudo", action="store_true",
                        help="Opt in to existing sudo -n rights; never prompts")
    args = parser.parse_args(argv)
    result = audit(args.noninteractive_sudo)
    print(json.dumps(result, sort_keys=True))
    return 2  # Always fail closed pending full app-reference scan & review.


if __name__ == "__main__":
    raise SystemExit(main())
