#!/usr/bin/env python3
"""One-time, auditable migration of missing v1 Homarr entries into Backstage.

Use an immutable pre-cutover Homarr snapshot as migration *input*, not a
permanent authority. Only migrate entries with an explicit Compose service
and x-nabla identity; do not invent runtime state from observed data.
Keep other YAML/Compose text intact through surgical labels changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from nabla_ops.catalog_exports import load_backstage_entities  # noqa: E402


def service_block(text: str, name: str) -> tuple[int, int]:
    header = re.compile(r"(?m)^  " + re.escape(name) + r":(?:\s*(?:#.*)?)?$")
    match = header.search(text)
    if not match:
        raise ValueError(f"cannot locate exact Compose service {name!r}")
    start = match.start()
    boundary = re.search(r"(?m)^  [A-Za-z0-9_.-]+:(?:\s*(?:#.*)?)?$",
                         text[match.end():])
    end = match.end() + boundary.start() if boundary else len(text)
    return start, end


def add_label(text: str, service_name: str, ref: str) -> str:
    start, end = service_block(text, service_name)
    block = text[start:end]
    if "com.albandrieu.nabla.entity-ref:" in block or "com.albandrieu.nabla.entity-ref=" in block:
        if ref not in block:
            raise ValueError(f"conflicting entity-ref for {service_name}")
        return text
    label_header = re.search(r"(?m)^    labels:\s*$", block)
    if label_header:
        insertion = label_header.end()
        # Existing labels can be mapping or Compose list; keep original syntax.
        rest = block[insertion:]
        first = re.search(r"(?m)^      (\S.*)$", rest)
        is_list = bool(first and first.group(1).startswith("- "))
        label = (f"\n      - com.albandrieu.nabla.entity-ref={ref}"
                 if is_list else f"\n      com.albandrieu.nabla.entity-ref: {ref}")
        block = block[:insertion] + label + block[insertion:]
    else:
        first_line = block.find("\n")
        if first_line == -1:
            raise ValueError(f"malformed Compose service block {service_name}")
        block = (block[:first_line+1]
                 + f"    labels:\n      com.albandrieu.nabla.entity-ref: {ref}\n"
                 + block[first_line+1:])
    return text[:start] + block + text[end:]


def materialize(root: Path, legacy: dict) -> dict:
    files = [root / "catalog/catalog-info.yaml"]
    files += sorted((root / "apps").glob("*/catalog-info.yaml"))
    entities = load_backstage_entities(path for path in files if path.is_file())
    existing = {entry["metadata"]["name"] for entry in entities}
    migrated: list[str] = []
    touched: set[str] = set()
    pending_docs: dict[Path, list[dict]] = {}
    compose_texts: dict[Path, str] = {}
    applications = legacy.get("applications")
    if not isinstance(applications, list):
        raise ValueError("legacy snapshot must have applications")
    for app in sorted(applications, key=lambda item: str(item.get("id", ""))):
        name = app.get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"invalid legacy Homarr ID: {name!r}")
        if name in existing:
            continue
        relative = app.get("sourcePath")
        service_name = app.get("composeService")
        if (not isinstance(relative, str)
                or not re.fullmatch(r"apps/[a-z0-9_-]+/compose\.ya?ml", relative)
                or not isinstance(service_name, str)):
            raise ValueError(f"{name}: cannot migrate without explicit Compose provenance")
        compose = root / relative
        if compose not in compose_texts:
            compose_texts[compose] = compose.read_text(encoding="utf-8")
        source = yaml.safe_load(compose_texts[compose])
        native = (source.get("services") or {}).get(service_name)
        if not isinstance(native, dict):
            raise ValueError(f"{name}: missing Compose service {service_name}")
        metadata = native.get("x-nabla")
        if not isinstance(metadata, dict) or not metadata.get("id"):
            raise ValueError(f"{name}: missing explicit legacy identity")
        status = metadata.get("status", "active")
        if status not in {"active", "planned", "disabled"}:
            raise ValueError(f"{name}: invalid declared operational-state {status!r}")
        criticality = metadata.get("criticality", "medium")
        if criticality not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{name}: invalid criticality {criticality!r}")
        kind = ("Resource" if name in {
            "mongo", "elasticsearch", "opensearch", "minio", "loki", "mimir", "tempo"
        } else "Component")
        ref = f"{kind.lower()}:default/{name}"
        compose_texts[compose] = add_label(compose_texts[compose], service_name, ref)
        doc_path = root / "apps" / Path(relative).parts[1] / "catalog-info.yaml"
        tags = [str(app.get("group") or "infrastructure").lower()]
        descriptor = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": kind,
            "metadata": {
                "name": name,
                "title": app.get("name") or name,
                "labels": {
                    "albandrieu.com/operational-state": status,
                    "albandrieu.com/operational-criticality": criticality,
                    **({"albandrieu.com/bia-scope": "inherited"} if status == "active" else {}),
                },
                "tags": tags,
            },
            "spec": {
                "type": str(metadata.get("kind") or "service"),
                **({"lifecycle": "experimental" if status != "active" else "production"}
                   if kind == "Component" else {}),
                "owner": "group:default/nabla-platform",
                "system": "system:default/nabla-homelab",
            },
        }
        description = metadata.get("description") or app.get("description")
        if isinstance(description, str) and description.strip():
            descriptor["metadata"]["description"] = description.strip()
        href = app.get("href")
        if isinstance(href, str) and href.startswith(("https://", "http://")):
            descriptor["metadata"]["links"] = [{"url": href, "title": "Application"}]
        pending_docs.setdefault(doc_path, []).append(descriptor)
        migrated.append(name)
        touched.add(relative)
        existing.add(name)

    for path, text in compose_texts.items():
        path.write_text(text, encoding="utf-8")
    for path, descriptors in pending_docs.items():
        original = path.read_text(encoding="utf-8") if path.is_file() else ""
        text = original.rstrip() + ("\n---\n" if original.strip() else "---\n")
        text += "".join(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
                        + ("---\n" if idx < len(descriptors)-1 else "")
                        for idx, doc in enumerate(descriptors))
        path.write_text(text, encoding="utf-8")
    return {"migrated": migrated, "composeFilesUpdated": sorted(touched)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--legacy-homarr-json", required=True, type=Path)
    args = parser.parse_args()
    legacy = json.loads(args.legacy_homarr_json.read_text(encoding="utf-8"))
    print(json.dumps(materialize(args.root, legacy), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
