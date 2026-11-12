#!/usr/bin/env python3
"""Register the per-application LiteLLM virtual keys of config/litellm/app-keys.json.

Run with sudo on TrueNAS from the canonical checkout. Each value is read from the
consumer's runtime file, so its Vaultwarden item stays the only source; LiteLLM
stores the key once. Default is a read-only plan; --apply registers only the keys
LiteLLM answers 404 for and never regenerates one. Never prints credentials.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/litellm/app-keys.json"
_spec = importlib.util.spec_from_file_location(
    "openclaw_litellm_keys", Path(__file__).with_name("provision-openclaw-litellm-keys.py"))
lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lib)


def runtime_value(path, variable):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    value = None
    for line in text.splitlines():
        name, separator, raw = line.strip().partition("=")
        if separator and name == variable:
            value = lib.dotenv_value(raw)
    return value or None


def register(spec, master, apply):
    label = spec["alias"].replace("-", "_")
    value = runtime_value(spec["runtimeFile"], spec["variable"])
    if not value:
        print(label + "_value=missing_in_runtime_file")
        return 2
    if value == master:
        print(label + "_credential_separation=failed")
        return 2
    key_id = hashlib.sha256(value.encode("utf-8")).hexdigest()
    status, payload = lib.request("/key/info?key=" + key_id, master)
    info = payload.get("info") if isinstance(payload, dict) else None
    if status == 200 and isinstance(info, dict):
        scoped = set(info.get("models") or []) == set(spec["models"])
        print(label + "_presence=existing")
        print(label + "_model_scope=" + ("verified" if scoped else "mismatch"))
        return 0 if scoped else 2
    if status != 404:
        print(label + "_presence=unverified")
        return 2
    print(label + "_presence=missing")
    if not apply:
        print(label + "_registration=planned")
        return 0
    code, _ = lib.request("/key/generate", master, {
        "key": value,
        "key_alias": spec["alias"],
        "models": spec["models"],
        "max_budget": spec["maxBudgetUsd"],
        "budget_duration": spec["budgetDuration"],
        "metadata": {"managed_by": "nabla-compose", "purpose": spec["alias"]},
    })
    print(label + "_registration_http=" + str(code or "unavailable"))
    return 0 if code in (200, 201) else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--alias", help="only this alias")
    args = parser.parse_args(argv)
    specs = [spec for spec in json.loads(CONFIG.read_text(encoding="utf-8"))["keys"]
             if args.alias in (None, spec["alias"])]
    if not specs:
        print("app_keys=none_selected")
        return 2
    master = (lib.container_environment() or {}).get("LITELLM_MASTER_KEY")
    if not master:
        print("litellm_master_key=unavailable")
        return 2
    return max(register(spec, master, args.apply) for spec in specs)


if __name__ == "__main__":
    sys.exit(main())
