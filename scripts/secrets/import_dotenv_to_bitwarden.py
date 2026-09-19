#!/usr/bin/env python3
"""Import one approved legacy dotenv materialization into Vaultwarden safely.

The command runs as the unlocked operator. If the legacy file is root-only it
uses sudo only to read that exact repository-discovered path. BW_SESSION is
removed from the sudo child environment. Secret values are never placed in
argv, logs, or the process environment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import audit_consumers
import import_env_to_bitwarden as importer
from render_from_bitwarden import BitwardenClient, SecretsError, load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update-existing", action="store_true")
    return parser.parse_args()


def app_spec(manifest: dict[str, Any], app: str) -> dict[str, Any]:
    matches = [item for item in manifest["items"] if item["app"] == app]
    if len(matches) != 1:
        raise SecretsError(
            f"expected exactly one manifest item for {app!r}, found {len(matches)}"
        )
    return matches[0]


def allowed_legacy_paths(manifest: dict[str, Any], app: str) -> list[Path]:
    report = audit_consumers.scan(ROOT, manifest)
    paths: set[Path] = set()
    for entry in report["legacyEnvFiles"]:
        entry_app, raw_path, _source = entry.split("|", 2)
        if entry_app == app:
            paths.add(Path(raw_path))
    canonical = Path(f"/mnt/cpool/secrets/runtime/{app}/.env.secrets")
    if canonical.exists():
        paths.add(canonical)
    return sorted(paths)


def choose_input(
    manifest: dict[str, Any],
    app: str,
    requested: Path | None,
) -> Path:
    allowed = allowed_legacy_paths(manifest, app)
    if requested is not None:
        requested_text = str(requested)
        for candidate in allowed:
            if str(candidate) == requested_text:
                return candidate
        raise SecretsError(
            f"{requested} is not an approved discovered legacy/canonical path for {app}; "
            f"allowed={','.join(str(path) for path in allowed) or '<none>'}"
        )
    if len(allowed) != 1:
        raise SecretsError(
            f"{app}: expected exactly one discovered source path when --input is omitted; "
            f"found {len(allowed)}: {', '.join(str(path) for path in allowed) or '<none>'}"
        )
    return allowed[0]


def read_root_bounded(path: Path) -> str:
    if path.is_file() and os.access(path, os.R_OK):
        return path.read_text(encoding="utf-8")

    child_env = os.environ.copy()
    child_env.pop("BW_SESSION", None)
    try:
        result = subprocess.run(
            ["sudo", "cat", "--", str(path)],
            check=True,
            capture_output=True,
            text=True,
            env=child_env,
        )
    except FileNotFoundError as exc:
        raise SecretsError("sudo is required to read the root-owned legacy file") from exc
    except subprocess.CalledProcessError as exc:
        raise SecretsError(
            f"cannot read approved legacy source {path}: "
            f"{(exc.stderr or '').strip() or exc.returncode}"
        ) from exc
    return result.stdout


def decode_dotenv_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        body = value[1:-1]
        out: list[str] = []
        index = 0
        while index < len(body):
            if body[index] == "\\" and index + 1 < len(body):
                out.append(body[index + 1])
                index += 2
                continue
            out.append(body[index])
            index += 1
        return "".join(out)
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = value[1:-1]
        if not isinstance(decoded, str):
            raise SecretsError("quoted dotenv value did not decode to a string")
        return decoded
    return value


def parse_dotenv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise SecretsError("legacy dotenv contains a non-assignment line")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            raise SecretsError(f"invalid dotenv key: {key!r}")
        value = decode_dotenv_value(raw_value)
        if "\x00" in value or "\n" in value or "\r" in value:
            raise SecretsError(f"{key}: multiline/NUL secret is unsupported")
        if key in result and result[key] != value:
            raise SecretsError(f"duplicate dotenv key with conflicting values: {key}")
        result[key] = value
    return result


def collect_values(
    spec: dict[str, Any],
    parsed: dict[str, str],
) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    supplied_sources: set[str] = set()
    missing: list[str] = []

    for secret in spec["secrets"]:
        target = secret["env"]
        source = importer.source_env_name(secret)
        candidates = []
        for key in (target, source):
            if key in parsed and key not in candidates:
                candidates.append(key)

        if not candidates:
            if secret.get("allowEmpty", False):
                values[target] = ""
                continue
            missing.append(target)
            continue

        candidate_values = {parsed[key] for key in candidates}
        if len(candidate_values) != 1:
            raise SecretsError(
                f"{spec['app']}/{target}: target/import keys disagree in legacy source"
            )
        value = candidate_values.pop()
        if not value and not secret.get("allowEmpty", False):
            missing.append(target)
            continue
        values[target] = value
        supplied_sources.add(source)

    if missing:
        raise SecretsError(
            f"{spec['app']}: required manifest keys missing from legacy source: "
            + ", ".join(sorted(missing))
        )
    return values, supplied_sources


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        raise SecretsError(
            "run as the unlocked Vaultwarden operator, not root; sudo is used only "
            "for the approved legacy-file read"
        )

    manifest = load_manifest(MANIFEST)
    spec = app_spec(manifest, args.app)
    source = choose_input(manifest, args.app, args.input)
    parsed = parse_dotenv(read_root_bounded(source))
    values, supplied_sources = collect_values(spec, parsed)

    print(
        f"legacy import dry-run app={args.app} source={source} "
        f"mapped={len(supplied_sources)}/{len(spec['secrets'])}; values suppressed"
    )
    if not args.apply:
        return 0

    client = BitwardenClient(
        session=os.environ.get("BW_SESSION", ""),
        server=manifest["server"],
    )
    client.verify()
    folder = manifest["folder"]
    client.verify_folder(folder["id"], folder["name"])

    matches = importer.exact_items(
        client,
        name=spec["item"],
        folder_id=folder["id"],
    )
    if len(matches) > 1:
        raise SecretsError(f"{args.app}: duplicate exact Vaultwarden items")
    existing = matches[0] if matches else None
    payload = importer.make_item(
        app_spec=spec,
        folder_id=folder["id"],
        values=values,
        existing=existing,
        supplied_source_names=supplied_sources,
    )

    if existing is None:
        importer.create_item(client, payload)
        print(f"created Vaultwarden item: {spec['item']}")
    else:
        if not args.update_existing:
            raise SecretsError(
                f"{args.app}: item already exists; use --update-existing after review"
            )
        item_id = existing.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise SecretsError(f"{args.app}: existing item has no id")
        importer.edit_item(client, item_id=item_id, payload=payload)
        print(f"updated Vaultwarden item: {spec['item']}")

    importer.sync_after_write(client, [spec["item"]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecretsError as exc:
        raise SystemExit(f"error: {exc}") from exc
