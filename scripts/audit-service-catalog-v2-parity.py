"""Audit catalog-v2 migration coverage without changing runtime state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops.catalog_v2 import (  # noqa: E402
    backstage_graph_errors,
    build_parity_report,
    compatibility_relation_debt,
    desired_exposure_errors,
    preparation_errors,
)

LEGACY_CATALOG = ROOT / "catalog" / "homelab-services.json"
EXPOSURE_OVERRIDES = ROOT / "catalog" / "homelab-exposure-overrides.json"
GENERATED_CATALOG = ROOT / "catalog" / "services.json"


def _backstage_entities() -> list[dict]:
    paths = [ROOT / "catalog" / "catalog-info.yaml"]
    paths.extend(sorted((ROOT / "apps").glob("*/catalog-info.yaml")))
    result: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        for index, payload in enumerate(
            yaml.safe_load_all(path.read_text(encoding="utf-8"))
        ):
            if payload is None:
                continue
            if not isinstance(payload, dict):
                raise ValueError(
                    f"{path.relative_to(ROOT)} document {index} must be a mapping"
                )
            result.append(payload)
    return result


def _label_map(service: dict) -> dict[str, str]:
    raw = service.get("labels") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    result: dict[str, str] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and "=" in item:
                key, value = item.split("=", 1)
                result[key] = value
    return result


def _compose_relation_bindings() -> list[dict]:
    result: list[dict] = []
    paths = sorted((ROOT / "apps").glob("*/compose*.yml"))
    paths.extend(sorted((ROOT / "apps").glob("*/compose*.yaml")))
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        services = payload.get("services")
        if not isinstance(services, dict):
            continue
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            entity_ref = _label_map(service).get(
                "com.albandrieu.nabla.entity-ref",
                "",
            )
            metadata = service.get("x-nabla")
            relations = metadata.get("relations") if isinstance(metadata, dict) else None
            if not entity_ref or not isinstance(relations, list):
                continue
            result.append(
                {
                    "sourcePath": path.relative_to(ROOT).as_posix(),
                    "composeService": str(service_name),
                    "entityRef": entity_ref,
                    "relations": relations,
                }
            )
    return result


def _compose_exposure_bindings() -> list[dict]:
    result: list[dict] = []
    paths = sorted((ROOT / "apps").glob("*/compose*.yml"))
    paths.extend(sorted((ROOT / "apps").glob("*/compose*.yaml")))
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        services = payload.get("services")
        if not isinstance(services, dict):
            continue
        for service_name, service in services.items():
            if not isinstance(service, dict):
                continue
            metadata = service.get("x-nabla")
            exposure = metadata.get("exposure") if isinstance(metadata, dict) else None
            if exposure is None:
                continue

            named_ports: list[str] = []
            raw_ports = service.get("ports")
            if isinstance(raw_ports, list):
                for port in raw_ports:
                    if isinstance(port, dict):
                        name = str(port.get("name") or "").strip()
                        if name:
                            named_ports.append(name)

            result.append(
                {
                    "sourcePath": path.relative_to(ROOT).as_posix(),
                    "composeService": str(service_name),
                    "entityRef": _label_map(service).get(
                        "com.albandrieu.nabla.entity-ref",
                        "",
                    ),
                    "namedPorts": sorted(set(named_ports)),
                    "exposure": exposure,
                }
            )
    return result


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail only on unclassified fields, malformed sources or orphan overrides",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the complete machine-readable parity inventory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the deterministic JSON report to this path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        backstage_entities = _backstage_entities()
        report = build_parity_report(
            _load(LEGACY_CATALOG),
            _load(EXPOSURE_OVERRIDES),
            _load(GENERATED_CATALOG),
            backstage_entities,
        )
        report["errors"] = sorted(
            set(report["errors"]) | set(backstage_graph_errors(backstage_entities))
        )
        exposure_errors = desired_exposure_errors(
            backstage_entities,
            _compose_exposure_bindings(),
        )
        report["errors"] = sorted(set(report["errors"]) | set(exposure_errors))
        report["summary"]["desiredExposureSpecErrors"] = len(exposure_errors)

        relation_debt = compatibility_relation_debt(
            backstage_entities,
            _compose_relation_bindings(),
        )
        report["compatibilityRelationDebt"] = relation_debt
        report["summary"]["compatibilityRelationDebt"] = len(relation_debt)
        if relation_debt:
            report["cutoverBlockers"].append(
                "legacy x-nabla relations still duplicate canonical Backstage dependencies"
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: catalog-v2 parity audit failed: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")

    if args.json:
        print(rendered, end="")
    else:
        summary = report["summary"]
        print(
            "catalog-v2 preparation:"
            f" legacy={summary['legacyServices']}"
            f" overrides={summary['exposureOverrides']}"
            f" explicit-id={summary['explicitIdMatches']}"
            f" slug-debt={summary['legacySlugMatches']}"
            f" name-debt={summary['legacyNameMatches']}"
            f" unmapped={summary['unmappedServices']}"
            f" backstage={summary['backstageEntities']}"
            f" materialized={summary['backstageMaterializedEntries']}"
            f" identity-ready={summary['identityReadyEntries']}"
            f" relation-debt={summary['compatibilityRelationDebt']}"
            f" exposure-spec-errors={summary['desiredExposureSpecErrors']}"
            f" desired-exposure={summary['desiredExposureEntries']}"
        )
        if summary["identityDebt"]:
            print(
                "warning:"
                f" {summary['identityDebt']} legacy entries still require stable"
                " v2 identity review before destructive cutover",
                file=sys.stderr,
            )
        if summary["compatibilityRelationDebt"]:
            print(
                "warning:"
                f" {summary['compatibilityRelationDebt']} legacy relation copies remain"
                " temporarily for v1 compatibility",
                file=sys.stderr,
            )

    errors = preparation_errors(report)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1 if args.check else 0

    if args.check:
        print("catalog-v2 preparation coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
