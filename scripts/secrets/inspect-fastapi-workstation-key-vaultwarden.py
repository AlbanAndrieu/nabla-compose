#!/usr/bin/env python3
"""Readonly equality check: issued Workstation scoped key vs Vaultwarden field.

No bw edit/create, Docker restart, key provisioning, model request or output
of secret material. The Bitwarden client may refresh its local CLI cache.
Run as the unprivileged Workstation operator with a NEW valid BW_SESSION.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import stat

try:
    from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".", 1)[0] != "jsonschema":
        raise
    BitwardenClient = None
    SecretsError = RuntimeError
    load_manifest = None

ROOT = Path(__file__).resolve().parents[2]
KEY_PATH = Path(".local/share/nabla-compose/fastapi-litellm/workstation.key")
MANIFEST = ROOT / "config/secrets/manifest.json"
ITEM = "nabla/prod/litellm"
FIELD = "LITELLM_FASTAPI_WORKSTATION_API_KEY"
APP = "litellm"


class Blocked(Exception):
    """Expected, value-blind local security failure."""


def read_private_key(home: Path) -> str:
    """Open only the specific user-owned 0600 file; never emit its contents."""
    if home.is_symlink() or not home.is_dir():
        raise Blocked("unsafe_home")
    target = home / KEY_PATH
    directory = home
    for part in KEY_PATH.parts[:-1]:
        directory = directory / part
        try:
            mode = directory.lstat()
        except OSError:
            raise Blocked("private_key_unavailable") from None
        if (not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.geteuid()
                or mode.st_mode & 0o022):
            raise Blocked("unsafe_key_path")
    if directory.stat().st_mode & 0o077:
        raise Blocked("unsafe_key_path")
    fd = -1
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or not 10 <= metadata.st_size <= 4096):
            raise Blocked("unsafe_key_file")
        value = os.read(fd, 4097)
    except OSError:
        raise Blocked("private_key_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)
    if len(value) > 4096:
        raise Blocked("unsafe_key_file")
    try:
        key = value.decode("ascii")
    except UnicodeError:
        raise Blocked("unsafe_key_file") from None
    if not (key.startswith("sk-") and key.endswith("\n")
            and len(key) > 10 and key.count("\n") == 1
            and all(33 <= ord(ch) <= 126 for ch in key[:-1])):
        raise Blocked("unsafe_key_file")
    return key[:-1]


def inspect(item: dict, expected: str) -> str:
    fields = item.get("fields")
    if fields is None:
        return "field_absent"
    if not isinstance(fields, list):
        return "field_unverified_schema"
    matches = [x for x in fields if isinstance(x, dict)
               and x.get("name") == FIELD]
    if not matches:
        return "field_absent"
    if len(matches) != 1:
        return "field_duplicate"
    field = matches[0]
    if field.get("type") != 1:
        return "field_not_hidden"
    value = field.get("value")
    if not isinstance(value, str) or not value:
        return "field_empty"
    if any(ch in value for ch in ("\r", "\n", "\x00")):
        return "field_invalid_format"
    return ("field_matches_private_key"
            if hmac.compare_digest(expected, value)
            else "field_mismatch_no_overwrite")


def manifest_contract(manifest: dict) -> tuple[str, str]:
    specs = [item for item in manifest["items"] if item.get("app") == APP]
    if len(specs) != 1 or specs[0].get("item") != ITEM:
        raise Blocked("manifest_mismatch")
    matches = [field for field in specs[0].get("secrets", [])
               if field.get("env") == FIELD and field.get("field") == FIELD]
    if len(matches) != 1:
        raise Blocked("manifest_mismatch")
    folder = manifest.get("folder", {})
    if (folder.get("name") != "TrueNAS" or
            not isinstance(folder.get("id"), str) or not folder["id"]):
        raise Blocked("manifest_mismatch")
    return folder["id"], folder["name"]


def check() -> str:
    if os.geteuid() == 0:
        return "unprivileged_operator_required"
    if not os.getenv("BW_SESSION"):
        return "fresh_session_required"
    if load_manifest is None or BitwardenClient is None:
        return "python_dependency_unavailable"
    key = read_private_key(Path.home())
    manifest = load_manifest(MANIFEST)
    folder_id, folder_name = manifest_contract(manifest)
    client = BitwardenClient(session=os.environ["BW_SESSION"],
                             server=manifest["server"])
    client.verify()
    client.verify_folder(folder_id, folder_name)
    item = client.get_exact_item(ITEM, folder_id)
    return inspect(item, key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        result = check()
    except Blocked as exc:
        result = str(exc)
    except (SecretsError, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError):
        result = "vaultwarden_unverified"
    report = {
        "schema": "nabla-fastapi-workstation-key-vaultwarden-compare/v1",
        "field_state": result,
        "item": ITEM,
        "field": FIELD,
        "vaultwarden_written": False,
        "runtime_mutated": False,
        "local_cli_cache_may_sync": True,
        "secret_values_printed": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if result == "field_matches_private_key" else 2


if __name__ == "__main__":
    raise SystemExit(main())
