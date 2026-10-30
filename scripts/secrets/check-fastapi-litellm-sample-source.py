#!/usr/bin/env python3
"""Read-only, value-blind Vaultwarden source check for FastAPI's application key.

Run unprivileged with a pre-existing BW_SESSION. Never prints secret values,
item JSON, Vaultwarden CLI output, credentials or network error bodies.
No key generation, secret file writing, model requests or Docker operations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# The repo's pinned jsonschema dependency may live only in .venv.
# Missing dependencies must never be reported as a missing Vaultwarden key.
try:
    from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".", 1)[0] != "jsonschema":
        raise
    BitwardenClient = None
    SecretsError = RuntimeError
    load_manifest = None

MANIFEST = Path(__file__).resolve().parents[2] / "config/secrets/manifest.json"
APP = "sample-litellm"
ITEM = "nabla/prod/sample-litellm"
FIELD = "LITELLM_API_KEY"


def classify(item: dict) -> str:
    """Inspect only the named hidden field; return a fixed label."""
    fields = item.get("fields")
    if fields is None:
        return "field_absent"
    if not isinstance(fields, list):
        return "field_unverified"
    matches = [f for f in fields
               if isinstance(f, dict) and f.get("name") == FIELD]
    if not matches:
        return "field_absent"
    if len(matches) != 1:
        return "field_duplicate"
    field = matches[0]
    if field.get("type") != 1:  # Bitwarden hidden custom-field type
        return "field_not_hidden"
    value = field.get("value")
    if not isinstance(value, str) or not value.strip():
        return "field_empty"
    if any(ch in value for ch in (chr(13), chr(10), chr(0))):
        return "field_invalid_format"
    return "field_present_nonempty_hidden"


def check() -> str:
    if os.geteuid() == 0:
        return "unprivileged_operator_required"
    if not os.environ.get("BW_SESSION"):
        return "vaultwarden_session_unavailable"
    if load_manifest is None or BitwardenClient is None:
        return "python_dependency_unavailable"

    # Schema and field metadata must agree with the declared contract.
    manifest = load_manifest(MANIFEST)
    specs = [app for app in manifest["items"] if app.get("app") == APP]
    if len(specs) != 1 or specs[0].get("item") != ITEM:
        return "manifest_mismatch"
    entries = [field for field in specs[0].get("secrets", [])
               if field.get("env") == FIELD and field.get("field") == FIELD]
    if len(entries) != 1:
        return "manifest_mismatch"

    client = BitwardenClient(
        session=os.environ["BW_SESSION"], server=manifest["server"]
    )
    client.verify()
    client.verify_folder(manifest["folder"]["id"], manifest["folder"]["name"])
    return classify(client.get_exact_item(ITEM, manifest["folder"]["id"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        state = check()
    except (SecretsError, OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError):
        # Never print exceptions from a secrets integration.
        state = "vaultwarden_unverified"
    print(json.dumps({
        "schema": "nabla-fastapi-litellm-sample-source/v1",
        "source": "vaultwarden",
        "item": ITEM,
        "field": FIELD,
        "field_state": state,
        "secret_values_printed": False,
        "service_runtime_mutated": False,
        "model_requests_sent": 0,
    }, sort_keys=True))
    return 0 if state == "field_present_nonempty_hidden" else 2


if __name__ == "__main__":
    raise SystemExit(main())
