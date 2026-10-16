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
            business_criticality = unit.get("businessCriticality")
            if (
                criticality not in CRITICALITY
                or policy not in POLICIES
                or not isinstance(stateful, bool)
            ):
                findings.append(
                    f"{entry}: invalid unit criticality/stateful/upgradePolicy"
                )
            if not readonly and (
                len(services) != 1
                or criticality != "low"
                or stateful is not False
                or policy != "automatic"
                or business_criticality != "low"
            ):
                findings.append(
                    f"{entry}: unsafe automatic upgrade of stateful/critical/multi-container unit"
                )
            if readonly and policy == "excluded":
                findings.append(
                    f"{entry}: excluded unit cannot opt in even for monitoring"
                )
    # Unattended execution must remain impossible for the proposed POC.
    # The API proxy is read-only because POST=0, not because of a :ro socket.
    watchtower = root / "apps/watchtower/compose.yml"
    if watchtower.exists():
        conf = yaml.safe_load(watchtower.read_text(encoding="utf-8"))
        app = (conf.get("services") or {}).get("watchtower") or {}
        environment = app.get("environment") or {}
        required = {
            "WATCHTOWER_LABEL_ENABLE": "true",
            "WATCHTOWER_MONITOR_ONLY": "true",
            "WATCHTOWER_NO_PULL": "true",
            "WATCHTOWER_LABEL_TAKE_PRECEDENCE": "false",
            "WATCHTOWER_INCLUDE_STOPPED": "false",
            "DOCKER_HOST": "tcp://docker-socket-proxy:2375",
        }
        for key, value in required.items():
            if str(environment.get(key, "")).lower() != value:
                findings.append(f"watchtower: unsafe {key} setting")
        if "manual-audit" not in app.get("profiles", []):
            findings.append("watchtower: manual-audit profile required")
        if app.get("volumes") or app.get("ports") or app.get("privileged"):
            findings.append("watchtower: socket/ports/privileged not permitted")
        if labels_for(app).get(ENABLE) != "false":
            findings.append("watchtower: self-update label must be false")
        proxy_compose = root / "docker-compose.yml"
        if proxy_compose.exists():
            proxy_doc = yaml.safe_load(proxy_compose.read_text(encoding="utf-8"))
            proxy = (proxy_doc.get("services") or {}).get("docker-socket-proxy") or {}
            proxy_env = proxy.get("environment", {})
            if str(proxy_env.get("POST", "")).lower() not in {"0", "false"}:
                findings.append("docker-socket-proxy: POST must be disabled")
            if str(proxy_env.get("IMAGES", "")).lower() not in {"1", "true"}:
                findings.append("docker-socket-proxy: IMAGES GET must be enabled")
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
