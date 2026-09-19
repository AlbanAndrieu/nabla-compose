#!/usr/bin/env python3
"""Audit Compose secret consumers against the Vaultwarden metadata contract.

The scanner is intentionally static and value-blind:
- it never reads runtime secret files;
- it never contacts Vaultwarden;
- it reports names/paths only;
- the debt baseline is a ratchet, not a source of secret truth.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "config" / "secrets" / "manifest.json"
DEFAULT_BASELINE = ROOT / "config" / "secrets" / "debt-baseline.json"

VAR_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?:(:-|:\?|[-?])([^}]*))?\}")
MNT_ENV_RE = re.compile(r"(/mnt/cpool/[^\s'\"#,]+/\.env(?:\.[^\s'\"#,]+)?)")
REPO_ENV_RE = re.compile(r"((?:\./)?apps/[^\s'\"#,]+/\.env(?:\.[^\s'\"#,]+)?)")
MNT_PATH_RE = re.compile(r"(/mnt/cpool/[^\s'\"#,]+)")
SECRET_NAME_TOKENS = {
    "PASSWORD",
    "PASS",
    "TOKEN",
    "SECRET",
    "CREDENTIAL",
    "CREDENTIALS",
    "AUTH",
}
SECRET_NAME_SUFFIXES = (
    "_API_KEY",
    "_PRIVATE_KEY",
    "_CLIENT_SECRET",
    "_ACCESS_KEY",
    "_MASTER_KEY",
    "_ADMIN_KEY",
    "_ENCRYPTION_KEY",
    "_SIGNING_KEY",
)
SPECIAL_PATH_RE = re.compile(
    r"(?:secret|token|password|credential|private[-_.]?key|admin[-_.]?key|key\.pem)",
    re.IGNORECASE,
)


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"error: {message}")


def git_tracked_compose_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        fail(f"cannot enumerate tracked files with git: {exc}")

    paths: list[Path] = []
    for raw in result.stdout.splitlines():
        if not raw:
            continue
        path = Path(raw)
        name = path.name.lower()
        if path.parts and path.parts[0] == "apps":
            if name in {"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"}:
                paths.append(root / path)
            continue
        if path.parts and path.parts[0] == "bootstrap" and name in {"compose.yml", "compose.yaml"}:
            paths.append(root / path)
            continue
        if len(path.parts) == 1 and (
            name.startswith("compose.") or name.startswith("docker-compose")
        ) and name.endswith((".yml", ".yaml")):
            paths.append(root / path)

    return sorted(set(paths))


def app_id_for_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if len(relative.parts) >= 3 and relative.parts[0] == "apps":
        return relative.parts[1]
    return f"_root:{relative.as_posix()}"


def is_secret_variable(name: str) -> bool:
    if name.endswith(SECRET_NAME_SUFFIXES):
        return True
    tokens = set(name.split("_"))
    return bool(tokens & SECRET_NAME_TOKENS)


def strip_full_line_comment(line: str) -> str:
    return "" if line.lstrip().startswith("#") else line


def manifest_envs(manifest: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in manifest.get("items", []):
        app = item.get("app")
        if not isinstance(app, str):
            continue
        covered: set[str] = set()
        for secret in item.get("secrets", []):
            if not isinstance(secret, dict):
                continue
            for key in ("env", "importEnv"):
                value = secret.get(key)
                if isinstance(value, str):
                    covered.add(value)
        result[app] = covered

    for entry in manifest.get("bootstrap", []):
        if not isinstance(entry, dict):
            continue
        app = entry.get("app")
        env = entry.get("env")
        if isinstance(app, str) and isinstance(env, str):
            result.setdefault(app, set()).add(env)
    return result


def item_apps(manifest: dict[str, Any]) -> set[str]:
    return {
        str(item["app"])
        for item in manifest.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("app"), str)
    }


def fingerprint(app: str, value: str, source: str) -> str:
    return f"{app}|{value}|{source}"


def scan(root: Path, manifest: dict[str, Any]) -> dict[str, list[str]]:
    managed_envs = manifest_envs(manifest)
    managed_apps = item_apps(manifest)

    legacy_env_files: set[str] = set()
    unmanaged_secret_variables: set[str] = set()
    insecure_defaults: set[str] = set()
    special_host_secret_files: set[str] = set()
    canonical_runtime_without_manifest: set[str] = set()
    compose_apps: set[str] = set()

    for path in git_tracked_compose_files(root):
        relative = path.relative_to(root).as_posix()
        app = app_id_for_path(root, path)
        compose_apps.add(app)
        text = path.read_text(encoding="utf-8")

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = strip_full_line_comment(raw_line)
            if not line:
                continue
            source = f"{relative}:{line_number}"

            env_paths = set(MNT_ENV_RE.findall(line)) | set(REPO_ENV_RE.findall(line))
            for env_path in env_paths:
                canonical_prefix = f"/mnt/cpool/secrets/runtime/{app}/"
                if env_path.startswith("/mnt/cpool/secrets/runtime/"):
                    if app.startswith("_root:") or not env_path.startswith(canonical_prefix):
                        canonical_runtime_without_manifest.add(
                            fingerprint(app, env_path, source)
                        )
                    elif app not in managed_apps:
                        canonical_runtime_without_manifest.add(
                            fingerprint(app, env_path, source)
                        )
                else:
                    legacy_env_files.add(fingerprint(app, env_path, source))

            for match in VAR_RE.finditer(line):
                variable, operator, default = match.groups()
                if not is_secret_variable(variable):
                    continue

                if app not in managed_envs or variable not in managed_envs[app]:
                    unmanaged_secret_variables.add(
                        fingerprint(app, variable, source)
                    )

                if operator == ":-" and default and default.strip():
                    insecure_defaults.add(
                        fingerprint(app, f"{variable}={default.strip()}", source)
                    )

            for candidate in MNT_PATH_RE.findall(line):
                if candidate in env_paths:
                    continue
                if SPECIAL_PATH_RE.search(candidate):
                    special_host_secret_files.add(
                        fingerprint(app, candidate, source)
                    )

    manifest_only_apps = sorted(
        app for app in managed_apps if app not in compose_apps
    )

    return {
        "legacyEnvFiles": sorted(legacy_env_files),
        "unmanagedSecretVariables": sorted(unmanaged_secret_variables),
        "insecureDefaults": sorted(insecure_defaults),
        "specialHostSecretFiles": sorted(special_host_secret_files),
        "canonicalRuntimeWithoutManifest": sorted(canonical_runtime_without_manifest),
        "manifestOnlyApps": manifest_only_apps,
    }


def debt_only(report: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        key: report[key]
        for key in (
            "legacyEnvFiles",
            "unmanagedSecretVariables",
            "insecureDefaults",
            "specialHostSecretFiles",
            "canonicalRuntimeWithoutManifest",
        )
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing JSON file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"{path} must contain a JSON object")
    return data


def compare_baseline(
    current: dict[str, list[str]],
    baseline: dict[str, Any],
) -> list[str]:
    if baseline.get("schemaVersion") != 1:
        fail("secret debt baseline schemaVersion must be 1")

    errors: list[str] = []
    for key, values in current.items():
        expected_raw = baseline.get(key, [])
        if not isinstance(expected_raw, list) or not all(
            isinstance(item, str) for item in expected_raw
        ):
            fail(f"baseline {key} must be a string list")
        expected = set(expected_raw)
        actual = set(values)
        new = sorted(actual - expected)
        resolved = sorted(expected - actual)
        if new:
            errors.append(f"{key}: new debt: {', '.join(new)}")
        if resolved:
            errors.append(
                f"{key}: baseline is stale; remove resolved debt: {', '.join(resolved)}"
            )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--json", action="store_true", help="print complete JSON report")
    parser.add_argument(
        "--print-baseline",
        action="store_true",
        help="print the current debt in baseline-file format",
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        help="fail on new debt and on stale resolved baseline entries",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest)
    report = scan(ROOT, manifest)
    debt = debt_only(report)

    if args.print_baseline:
        print(json.dumps({"schemaVersion": 1, **debt}, indent=2, sort_keys=True))
        return 0

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))

    if args.check_baseline:
        baseline = load_json(args.baseline)
        errors = compare_baseline(debt, baseline)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            print(
                "Current suggested baseline follows; review before updating:",
                file=sys.stderr,
            )
            print(
                json.dumps({"schemaVersion": 1, **debt}, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 1

    if not args.json:
        counts = {key: len(value) for key, value in report.items()}
        print(
            "secret-consumer audit: "
            + " ".join(f"{key}={counts[key]}" for key in sorted(counts))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
