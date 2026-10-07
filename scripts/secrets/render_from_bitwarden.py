#!/usr/bin/env python3
"""Render short-lived Docker Compose env files from Vaultwarden via Bitwarden CLI."""

from __future__ import annotations

import argparse
from contextlib import suppress
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

MANIFEST_SCHEMA = (
    Path(__file__).resolve().parents[2] / "config" / "secrets" / "manifest.schema.json"
)


class SecretsError(RuntimeError):
    """Raised when secret metadata or retrieval is unsafe or ambiguous."""


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def validate_manifest(data: dict[str, Any]) -> None:
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(data)
    except SchemaError as exc:
        raise SecretsError(f"invalid manifest schema: {exc.message}") from exc
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise SecretsError(
            f"manifest schema violation at {location}: {exc.message}"
        ) from exc

    apps: set[str] = set()
    import_env_names: set[str] = set()
    for item in data["items"]:
        app = item["app"]
        if app in apps:
            raise SecretsError(f"duplicate app identifier: {app}")
        apps.add(app)

        app_env_names: set[str] = set()
        for secret in item["secrets"]:
            env_name = secret["env"]
            import_env = secret.get("importEnv", env_name)
            if env_name in app_env_names:
                raise SecretsError(f"{app}: duplicate environment variable: {env_name}")
            if import_env in import_env_names:
                raise SecretsError(
                    f"source environment variable mapped by multiple apps: {import_env}"
                )
            app_env_names.add(env_name)
            import_env_names.add(import_env)


class BitwardenClient:
    """Fail-closed wrapper around the official Bitwarden Password Manager CLI."""

    def __init__(self, *, session: str, server: str) -> None:
        if not session:
            raise SecretsError("BW_SESSION is required; run `bw unlock` first")
        self.session = session
        self.server = server.rstrip("/")

    def _run(
        self,
        *args: str,
        with_session: bool = False,
        input_text: str | None = None,
    ) -> str:
        command = ["bw", *args]
        child_env = os.environ.copy()
        if with_session:
            child_env["BW_SESSION"] = self.session

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=child_env,
                input=input_text,
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

        status = json.loads(self._run("status", with_session=True))
        if status.get("status") != "unlocked":
            raise SecretsError("Bitwarden vault is not unlocked")

        self._run("sync", with_session=True)

    def verify_folder(self, folder_id: str, expected_name: str) -> None:
        raw = self._run("list", "folders", with_session=True)
        matches = [
            folder
            for folder in json.loads(raw)
            if isinstance(folder, dict) and folder.get("id") == folder_id
        ]
        if len(matches) != 1:
            raise SecretsError(
                f"expected Vaultwarden folder id {folder_id!r}, found {len(matches)}"
            )
        actual_name = matches[0].get("name")
        if actual_name != expected_name:
            raise SecretsError(
                f"Vaultwarden folder mismatch: expected {expected_name!r}, got {actual_name!r}"
            )

    def get_exact_item(self, name: str, folder_id: str) -> dict[str, Any]:
        raw = self._run(
            "list",
            "items",
            "--search",
            name,
            "--folderid",
            folder_id,
            with_session=True,
        )
        matches = [
            item
            for item in json.loads(raw)
            if isinstance(item, dict)
            and item.get("name") == name
            and item.get("folderId") == folder_id
        ]
        if len(matches) != 1:
            raise SecretsError(
                f"expected exactly one Vaultwarden item named {name!r} in the TrueNAS folder, "
                f"found {len(matches)}"
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


def ensure_safe_output_target(target: Path) -> None:
    """Refuse writing secret material into a Git-trackable path.

    Rendering inside a worktree is allowed only when the exact target is ignored. This keeps
    historical ignored ``.env.secrets`` workflows possible while preventing an ad-hoc output
    such as ``./cyberbro.env.secrets`` from becoming an easy accidental commit candidate.
    """

    try:
        probe = subprocess.run(
            ["git", "-C", str(target.parent), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return

    if probe.returncode != 0:
        return

    repo_root = Path(probe.stdout.strip()).resolve()
    resolved_target = target.resolve(strict=False)
    try:
        relative_target = resolved_target.relative_to(repo_root)
    except ValueError:
        return

    ignored = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "check-ignore",
            "-q",
            "--no-index",
            "--",
            str(relative_target),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if ignored.returncode != 0:
        raise SecretsError(
            "refusing to render secret material to Git-trackable path "
            f"{target}; use /tmp, /run, a canonical runtime directory, or an ignored path"
        )


def write_env_file(
    *,
    app_spec: dict[str, Any],
    item: dict[str, Any],
    target: Path,
) -> Path:
    parent_existed = target.parent.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed:
        os.chmod(target.parent, 0o700)
    ensure_safe_output_target(target)

    lines = [
        "# Generated from Vaultwarden by scripts/secrets/render_from_bitwarden.py",
        "# Runtime materialization: do not commit this file.",
    ]
    for spec in app_spec["secrets"]:
        value = extract_secret(item, spec)
        lines.append(f"{spec['env']}={dotenv_literal(value)}")
    payload = "\n".join(lines) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{app_spec['app']}.",
        suffix=".tmp",
        dir=target.parent,
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
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
    return target


def render_app(
    *,
    app_spec: dict[str, Any],
    item: dict[str, Any],
    output_dir: Path,
) -> Path:
    return write_env_file(
        app_spec=app_spec,
        item=item,
        target=output_dir / f"{app_spec['app']}.env",
    )


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
        "--output-file",
        type=Path,
        help="write one selected app to an exact path, for example a TrueNAS service .env",
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
    if args.output_file and len(requested) != 1:
        raise SecretsError("--output-file requires exactly one --app")

    folder = manifest["folder"]
    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""),
        server=manifest["server"],
    )
    client.verify()
    client.verify_folder(folder["id"], folder["name"])

    for app_spec in manifest["items"]:
        if app_spec["app"] not in requested:
            continue
        item = client.get_exact_item(app_spec["item"], folder["id"])
        if args.output_file:
            target = write_env_file(
                app_spec=app_spec,
                item=item,
                target=args.output_file,
            )
        else:
            target = render_app(
                app_spec=app_spec,
                item=item,
                output_dir=args.output_dir,
            )
        print(f"rendered {app_spec['app']} -> {target}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
