#!/usr/bin/env python3
"""Fail closed for Watchtower container selection and Compose deployment units.

Selection is derived from Compose labels; a multi-container Compose project is
NEVER eligible for Watchtower automated recreation. This script does not deploy.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

ENABLE = "com.centurylinklabs.watchtower.enable"
MONITOR = "com.centurylinklabs.watchtower.monitor-only"
CRITICALITY = {"critical", "high", "medium", "low"}
POLICIES = {"excluded", "observe", "controlled", "automatic"}


def labels_for(config: dict) -> dict[str, str]:
    raw = config.get("labels", {})
    if isinstance(raw, dict):
        return {str(k): str(v).lower() for k, v in raw.items()}
    if isinstance(raw, list):
        result = {}
        for label in raw:
            if not isinstance(label, str) or "=" not in label:
                raise ValueError(f"invalid label {label!r}")
            key, value = label.split("=", 1)
            result[key] = value.lower()
        return result
    raise ValueError("labels must be a mapping or key=value list")


def audit(root: pathlib.Path) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    selected: list[str] = []
    for path in sorted(root.glob("apps/*/compose.y*ml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            findings.append(f"{path}: not a Compose mapping")
            continue
        services = doc.get("services", {})
        if not isinstance(services, dict):
            findings.append(f"{path}: services is not a mapping")
            continue
        unit = (doc.get("x-nabla") or {}).get("deploymentUnit") or {}
        if unit and not isinstance(unit, dict):
            findings.append(f"{path}: deploymentUnit must be a mapping")
            continue
        for name, conf in services.items():
            if not isinstance(conf, dict):
                continue
            label = labels_for(conf)
            enabled = label.get(ENABLE, "false") == "true"
            readonly = label.get(MONITOR, "false") == "true"
            if not enabled:
                continue
            entry = f"{path.relative_to(root)}:{name}"
            selected.append(f"{entry} [{'observe' if readonly else 'automatic'}]")
            if not unit:
                findings.append(
                    f"{entry}: selected container requires x-nabla.deploymentUnit"
                )
                continue
            criticality = unit.get("criticality")
            policy = unit.get("upgradePolicy")
            stateful = unit.get("stateful")
            if (
                criticality not in CRITICALITY
                or policy not in POLICIES
                or not isinstance(stateful, bool)
            ):
                findings.append(
                    f"{entry}: incomplete/invalid unit criticality, stateful or upgradePolicy"
                )
            if not readonly and (
                len(services) != 1
                or criticality != "low"
                or stateful is not False
                or policy != "automatic"
            ):
                findings.append(
                    f"{entry}: automatic upgrade requires one low-risk stateless service in an automatic unit"
                )
            if readonly and policy == "excluded":
                findings.append(
                    f"{entry}: excluded unit cannot opt in even for monitoring"
                )
    return findings, selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    violations, selected = audit(args.root)
    for line in selected:
        print("WATCHTOWER_SELECTED", line)
    for line in violations:
        print("ERROR", line, file=sys.stderr)
    if violations:
        return 1
    print(f"PASS watchtower unit policy ({len(selected)} selected containers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
