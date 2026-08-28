#!/usr/bin/env python3
"""Render short-lived Docker Compose env files from Vaultwarden via Bitwarden CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
ALLOWED_ROTATION = {"preserve", "rotatable"}


class SecretsError(RuntimeError):
    """Raised when secret metadata or retrieval is unsafe or ambiguous."""


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def validate_manifest(data: dict[str, Any]) -> None:
    if data.get("schemaVersion") != 1:
        raise SecretsError("manifest schemaVersion must be 1")

    server = data.get("server")
    if not isinstance(server, str) or not server.startswith("https://"):
        raise SecretsError("manifest server must be an https URL")

    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise SecretsError("manifest items must be a non-empty list")

    apps: set[str] = set()
    env_names: set[str] = set()
    forbidden_keys = {"value", "password", "token", "secretValue"}

    for item in items:
        if not isinstance(item, dict):
            raise SecretsError("manifest item entries must be objects")
        if forbidden_keys.intersection(item):
            raise SecretsError("manifest item contains a forbidden value-bearing key")

        app = item.get("app")
        item_name = item.get("item")
        secrets = item.get("secrets")

        if not isinstance(app, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", app):
            raise SecretsError(f"invalid app identifier: {app!r}")
        if app in apps:
            raise SecretsError(f"duplicate app identifier: {app}")
        apps.add(app)

        if not isinstance(item_name, str) or not item_name.startswith("nabla/"):
            raise SecretsError(f"{app}: item must use the nabla/... naming convention")
        if not isinstance(secrets, list) or not secrets:
            raise SecretsError(f"{app}: secrets must be a non-empty list")

        app_env_names: set[str] = set()
        for secret in secrets:
            if not isinstance(secret, dict):
                raise SecretsError(f"{app}: secret entries must be objects")
            if forbidden_keys.intersection(secret):
                raise SecretsError(f"{app}: secret metadata contains a forbidden value-bearing key")

            env_name = secret.get("env")
            field = secret.get("field")
            source = secret.get("source", "field")
            rotation = secret.get("rotation", "rotatable")

            if not isinstance(env_name, str) or not ENV_NAME_RE.fullmatch(env_name):
                raise SecretsError(f"{app}: invalid environment variable name: {env_name!r}")
            if env_name in app_env_names:
                raise SecretsError(f"{app}: duplicate environment variable: {env_name}")
            if env_name in env_names:
                raise SecretsError(f"environment variable mapped by multiple apps: {env_name}")
            app_env_names.add(env_name)
            env_names.add(env_name)

            if source not in {"field", "login.password", "login.username"}:
                raise SecretsError(f"{app}/{env_name}: unsupported source: {source}")
            if source == "field" and (not isinstance(field, str) or not field):
                raise SecretsError(f"{app}/{env_name}: field is required")
            if rotation not in ALLOWED_ROTATION:
                raise SecretsError(f"{app}/{env_name}: invalid rotation policy: {rotation}")


class BitwardenClient:
    """Fail-closed wrapper around the official Bitwarden Password Manager CLI."""

    def __init__(self, *, session: str, server: str) -> None:
        if not session:
            raise SecretsError("BW_SESSION is required; run `bw unlock` first")
        self.session = session
        self.server = server.rstrip("/")

    def _run(self, *args: str, with_session: bool = False) -> str:
        command = ["bw", *args]
        if with_session:
            command.extend(["--session", self.session])

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise SecretsError("Bitwarden CLI `bw` was not found in PATH") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise SecretsError(
                f"Bitwarden CLI command failed: {stderr or args[0]}"
            ) from exc
        return result.stdout.strip()

    def verify(self) -> None:
        configured_server = self._run("config", "server").rstrip("/")
        if configured_server != self.server:
            raise SecretsError(
                "Bitwarden CLI server mismatch: "
                f"expected {self.server}, got {configured_server or '<unset>'}"
            )

        status = json.loads(self._run("status"))
        if status.get("status") != "unlocked":
            raise SecretsError("Bitwarden vault is not unlocked")

        self._run("sync", with_session=True)

    def get_exact_item(self, name: str) -> dict[str, Any]:
        raw = self._run("list", "items", "--search", name, with_session=True)
        matches = [
            item
            for item in json.loads(raw)
            if isinstance(item, dict) and item.get("name") == name
        ]
        if len(matches) != 1:
            raise SecretsError(
                f"expected exactly one Vaultwarden item named {name!r}, found {len(matches)}"
            )
        return matches[0]


def extract_secret(item: dict[str, Any], spec: dict[str, Any]) -> str:
    source = spec.get("source", "field")
    if source == "login.password":
        value = (item.get("login") or {}).get("password")
    elif source == "login.username":
        value = (item.get("login") or {}).get("username")
    else:
        field_name = spec["field"]
        values = [
            field.get("value")
            for field in item.get("fields") or []
            if isinstance(field, dict) and field.get("name") == field_name
        ]
        if len(values) != 1:
            raise SecretsError(
                f"{item.get('name', '<unknown>')}: expected exactly one field {field_name!r}"
            )
        value = values[0]

    if not isinstance(value, str) or (not value and not spec.get("allowEmpty", False)):
        raise SecretsError(
            f"{item.get('name', '<unknown>')}/{spec['env']}: secret is empty or missing"
        )
    if "\x00" in value or "\n" in value or "\r" in value:
        raise SecretsError(
            f"{item.get('name', '<unknown>')}/{spec['env']}: multiline/NUL secrets are unsupported"
        )
    return value


def dotenv_literal(value: str) -> str:
    """Quote a Compose env-file value literally, without variable interpolation."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def render_app(
    *,
    app_spec: dict[str, Any],
    item: dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)

    target = output_dir / f"{app_spec['app']}.env"
    lines = [
        "# Generated from Vaultwarden by scripts/secrets/render_from_bitwarden.py",
        "# Ephemeral: do not commit or back up this file.",
    ]
    for spec in app_spec["secrets"]:
        value = extract_secret(item, spec)
        lines.append(f"{spec['env']}={dotenv_literal(value)}")
    payload = "\n".join(lines) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{app_spec['app']}.",
        suffix=".tmp",
        dir=output_dir,
        text=True,
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        os.chmod(target, 0o600)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/secrets/manifest.json"),
        help="metadata-only secret manifest",
    )
    parser.add_argument(
        "--app",
        action="append",
        dest="apps",
        help="render only this app; repeat for multiple apps (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/run/nabla-secrets"),
        help="ephemeral output directory (default: /run/nabla-secrets)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate manifest only; do not contact Vaultwarden",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)

    if args.check:
        print(f"validated {args.manifest}")
        return 0

    requested = set(args.apps or [item["app"] for item in manifest["items"]])
    known = {item["app"] for item in manifest["items"]}
    unknown = sorted(requested - known)
    if unknown:
        raise SecretsError(f"unknown app(s): {', '.join(unknown)}")

    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""),
        server=manifest["server"],
    )
    client.verify()

    for app_spec in manifest["items"]:
        if app_spec["app"] not in requested:
            continue
        item = client.get_exact_item(app_spec["item"])
        target = render_app(app_spec=app_spec, item=item, output_dir=args.output_dir)
        print(f"rendered {app_spec['app']} -> {target}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
