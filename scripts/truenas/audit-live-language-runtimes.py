#!/usr/bin/env python3
"""Read-only local Docker language runtime inventory for TrueNAS migration acceptance.

Uses docker ps/inspect and bounded --version probes. No Docker writes, reload,
image pulls, middleware calls, registry access, network or secret environment dumps.
An unavailable interpreter is UNKNOWN, not proof that the workload is patched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/upgrades/supported-runtime-targets.json"
PHP_VERSION = re.compile(r"PHP\s+(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)
PY_VERSION = re.compile(r"Python\s+(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


def classify(family: str, version: str, policy: dict) -> tuple[str, str]:
    """Interpret observed FULL semantic versions, never labels/major-only tags."""
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isascii() and p.isdecimal() for p in parts):
        return "unknown", "invalid or incomplete version"
    series = ".".join(parts[:2])
    config = policy["languageRuntimes"][family]
    if series in config.get("eolAtDate", []):
        return "eol", "unsupported runtime branch"
    floor = config.get("minimumPatched", {}).get(series)
    if floor and tuple(map(int, parts)) < tuple(map(int, floor.split("."))):
        return "critical-patch-missing", "below required patch " + floor
    if series in config.get("securityOnly", []):
        return "security-only", "maintenance-only runtime branch"
    if series in config.get("allowedSupported", []):
        return "supported", "maintained runtime branch"
    return "unknown", "unclassified runtime branch"


def _execute(args: list[str], timeout: int, *, output_limit: int = 512) -> tuple[int, str]:
    try:
        result = subprocess.run(args, check=False, capture_output=True,
                                text=True, timeout=timeout)
        # Never expose tool errors that could include environment/credentials.
        return result.returncode, result.stdout[:output_limit]
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return 127, ""


def probe(container: str, family: str, timeout: int) -> str | None:
    """Run a bounded version-only command as the container's default user."""
    binary = "php" if family == "php" else "python3"
    argv = ["docker", "exec", container, binary, "-v" if family == "php" else "--version"]
    code, out = _execute(argv, timeout)
    # Python --version may be written to stderr by old Python; no echo errors.
    if code != 0:
        return None
    regex = PHP_VERSION if family == "php" else PY_VERSION
    match = regex.search(out)
    return ".".join(match.groups()) if match else None


def inventory(policy: dict, timeout: int, limit: int) -> list[dict[str, str]]:
    code, data = _execute(["docker", "ps", "-q"], timeout=timeout,
                          output_limit=65536)
    if code != 0 or len(data) >= 65536:
        raise RuntimeError("cannot inspect complete running Docker inventory")
    names = [line.strip() for line in data.splitlines() if line.strip()]
    # Never silently report a partial fleet as fully scanned.
    if len(names) > limit:
        raise RuntimeError("running container count exceeds explicit inventory limit")
    rows: list[dict[str, str]] = []
    for container in names:
        if not re.fullmatch(r"[a-f0-9]{12,64}", container):
            raise RuntimeError("unexpected Docker container identifier")
        code, line = _execute(
            ["docker", "inspect", "--format", "{{.Name}}|{{.Config.Image}}|{{.Image}}",
             container], timeout=timeout)
        if code != 0 or "|" not in line:
            raise RuntimeError("cannot inspect Docker container metadata")
        label, image, digest = (line.strip().split("|", 2))
        if not label.startswith("/") or not digest.startswith("sha256:"):
            raise RuntimeError("untrusted Docker image metadata")
        row = {"container": label.lstrip("/"), "image": image,
               "imageId": digest, "php": "unknown", "python": "unknown",
               "phpVersion": "", "pythonVersion": ""}
        for family in ("php", "python"):
            version = probe(container, family, timeout)
            if version:
                row[family + "Version"] = version
                row[family], _ = classify(family, version, policy)
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only; default")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-containers", type=int, default=200)
    parser.add_argument("--timeout-seconds", type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.max_containers <= 500 or not 1 <= args.timeout_seconds <= 30:
        parser.error("container and timeout limits must stay bounded")
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        rows = inventory(policy, args.timeout_seconds, args.max_containers)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print("BLOCKED: live language inventory unavailable (" +
              type(exc).__name__ + ")", file=sys.stderr)
        return 2
    findings = [row for row in rows if row["php"] in ("eol", "critical-patch-missing")
                or row["python"] in ("eol", "critical-patch-missing")]
    unknown = [row for row in rows if row["php"] == "unknown"
               and row["python"] == "unknown"]
    report = {"readOnly": True, "containers": len(rows),
              "unverifiedContainers": len(unknown), "criticalFindings": len(findings),
              "runtimeAcceptance": False, "rows": rows}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Running containers={len(rows)} critical={len(findings)} "
              f"unknown-both={len(unknown)}")
        for row in rows:
            if row["php"] in ("eol", "critical-patch-missing") or row["python"] in ("eol", "critical-patch-missing"):
                print(f"BLOCKED {row['container']}: PHP {row['phpVersion']} "
                      f"({row['php']}), Python {row['pythonVersion']} ({row['python']})")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
