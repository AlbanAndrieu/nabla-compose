#!/usr/bin/env python3
"""Import one shared GitHub App PEM to Vaultwarden and prepare TrueNAS Cron runtime.

The key is a separate 0600 PEM, NOT an environment variable. The Cron
.env.secrets file is a 0600 reference contract, not a duplicated private key.
Default --check is offline; mutations require an unlocked Bitwarden operator.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/secrets"))
from import_env_to_bitwarden import create_item, exact_items, sync_after_write  # noqa: E402
from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest  # noqa: E402

ITEM = "nabla/prod/nabla-github-app"
RUNTIME = Path("/mnt/cpool/secrets/runtime/nabla-github-app")
REPOSITORIES = frozenset({
    "AlbanAndrieu/nabla-compose", "AlbanAndrieu/fastapi-sample",
    "AlbanAndrieu/nabla-site-alban", "AlbanAndrieu/nabla-site-bababou",
})
KEY = "github-app-private-key.pem"
META = "github-app.json"
ENV = ".env.secrets"


def file_contract(path: Path) -> None:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.stat().st_mode & 0o077):
        raise SecretsError("input must be an existing owner-only regular file")


def metadata(path: Path) -> dict:
    file_contract(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(config, dict) or set(config) != {
        "app_id", "installation_id", "repositories"
    } or type(config["app_id"]) is not int or config["app_id"] <= 0
            or type(config["installation_id"]) is not int
            or config["installation_id"] < 0
            or not isinstance(config["repositories"], list)
            or len(config["repositories"]) != len(REPOSITORIES)
            or set(config["repositories"]) != REPOSITORIES):
        raise SecretsError("GitHub App metadata or repo scope invalid")
    return config


def client_item():
    if os.geteuid() == 0:
        raise SecretsError("Vaultwarden operations require unlocked non-root operator")
    manifest = load_manifest(ROOT / "config/secrets/manifest.json")
    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""), server=manifest["server"]
    )
    client.verify()
    folder = manifest["folder"]
    client.verify_folder(folder["id"], folder["name"])
    found = exact_items(client, name=ITEM, folder_id=folder["id"])
    if len(found) > 1:
        raise SecretsError("multiple same-named GitHub App vault items")
    return client, folder["id"], (found[0] if found else None)


def upload(pem: Path, info: Path) -> None:
    metadata(info)
    file_contract(pem)
    if pem.stat().st_size > 16384 or pem.stat().st_size < 256:
        raise SecretsError("GitHub App PEM size invalid")
    data = pem.read_bytes()
    if b"BEGIN " not in data or b"PRIVATE KEY" not in data:
        raise SecretsError("GitHub App PEM header not present")
    client, folder, item = client_item()
    if item is None:
        create_item(client, {
            "name": ITEM, "type": 1, "folderId": folder,
            "login": {"username": "nabla-github-app", "password": None,
                      "uris": [{"uri": "https://github.com/settings/apps"}]},
            "fields": [],
        })
        if not sync_after_write(client, [ITEM]):
            raise SecretsError("vault item created but sync unverified")
        client, folder, item = client_item()
    if item is None or not isinstance(item.get("id"), str):
        raise SecretsError("GitHub App vault item creation failed")
    if any(a.get("fileName") == KEY for a in (item.get("attachments") or [])):
        print("EXISTS: private PEM already attached; do not silently rotate")
        return
    # Bitwarden CLI creates a *ciphertext attachment* on a known item.
    # The PEM filename (not its bytes) is passed in the command line.
    client._run(
        "create", "attachment", "--file", str(pem), "--itemid", item["id"],
        with_session=True,
    )
    if not sync_after_write(client, [ITEM]):
        raise SecretsError("PEM attachment upload accepted but sync not verified")
    print("PASS: GitHub App PEM attached in Vaultwarden; secret suppressed")


def privileged(*args: str) -> None:
    try:
        subprocess.run(
            ["sudo", "-n", *args], check=True, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise SecretsError("privileged TrueNAS install failed; no secret printed") from None


def materialize(info: Path, *, fastapi_approved: bool) -> None:
    metadata(info)
    client, _, item = client_item()
    if item is None or not isinstance(item.get("id"), str):
        raise SecretsError("GitHub App Vaultwarden item absent")
    attachments = [
        a for a in item.get("attachments") or []
        if isinstance(a, dict) and a.get("fileName") == KEY
    ]
    if len(attachments) != 1:
        raise SecretsError("exactly one GitHub App PEM attachment required")
    with tempfile.TemporaryDirectory(prefix="nabla-ghapp-", dir=None) as tmp:
        staging = Path(tmp)
        staging.chmod(0o700)
        staged_key = staging / KEY
        client._run(
            "get", "attachment", KEY, "--itemid", item["id"],
            "--output", str(staged_key), with_session=True,
        )
        staged_key.chmod(0o600)
        file_contract(staged_key)
        if staged_key.stat().st_size < 256:
            raise SecretsError("downloaded PEM too small")
        ref = staging / ENV
        ref.write_text(
            "# Cron launcher references only; never copy a PEM into dotenv\n"
            f"GITHUB_APP_CONFIG_FILE={RUNTIME / META}\n"
            f"GITHUB_APP_PRIVATE_KEY_FILE={RUNTIME / KEY}\n"
            f"DEFECTDOJO_FASTAPI_PULL_APPROVED={'YES' if fastapi_approved else 'NO'}\n",
            encoding="utf-8",
        )
        ref.chmod(0o600)
        privileged("install", "-d", "-m", "0700", "-o", "root", "-g", "root", str(RUNTIME))
        for source, name in ((staged_key, KEY), (info, META), (ref, ENV)):
            destination = RUNTIME / name
            # Never overwrite a rotated or separately reconciled secret.
            check = subprocess.run(
                ["sudo", "-n", "test", "-e", str(destination)],
                capture_output=True, check=False, timeout=10,
            )
            if check.returncode == 0:
                privileged("cmp", "-s", str(source), str(destination))
                continue
            if check.returncode != 1:
                raise SecretsError("cannot verify existing runtime file")
            privileged("install", "-m", "0600", "-o", "root", "-g", "root",
                       str(source), str(destination))
    print("PASS: TrueNAS root-only PEM, metadata and Cron .env.secrets references installed")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check", action="store_true")
    choice.add_argument("--import-vaultwarden", action="store_true")
    choice.add_argument("--materialize", action="store_true")
    p.add_argument("--pem", type=Path)
    p.add_argument("--metadata", type=Path)
    p.add_argument("--approve-fastapi", action="store_true")
    args = p.parse_args()
    if args.check:
        print("CHECK: one GitHub App for four repos; Vaultwarden PEM attachment + 0600 runtime references")
        return 0
    if args.metadata is None:
        p.error("--metadata required for the selected operation")
    if args.import_vaultwarden:
        if args.pem is None:
            p.error("--pem required for Vaultwarden import")
        upload(args.pem, args.metadata)
    else:
        materialize(args.metadata, fastapi_approved=args.approve_fastapi)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SecretsError, OSError, ValueError) as exc:
        raise SystemExit(f"REJECTED: {exc}") from None
