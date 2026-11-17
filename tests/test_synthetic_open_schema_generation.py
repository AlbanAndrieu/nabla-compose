"""Contract tests for generated outside-in Synthetic Open Schema resources."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate-synthetic-open-schema.py"
CATALOG = ROOT / "catalog" / "generated" / "entities.json"

SPEC = importlib.util.spec_from_file_location("generate_sos", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_generator_covers_every_enabled_public_https_exposure() -> None:
    resources = MODULE.generate_resources(_catalog())

    by_kind: dict[str, list[dict]] = {}
    for resource in resources:
        by_kind.setdefault(resource["kind"], []).append(resource)

    public_count = sum(
        MODULE._public_url(service) is not None
        for service in MODULE._backstage_public_services(_catalog())
        if isinstance(service, dict)
    )
    # Garage S3 API and Admin API are internal-only since #254 (no public route).
    # 2026-11-04: ddns-updater, ollama, ollama-gpu (Access-protected) and the
    # TrueNAS FastAPI Sample observer were declared external; hello.int is an
    # explicit direct (non-Access) exception. 2026-11-05: LiteLLM is no longer
    # published on the Internet (owner decision). 2026-11-13: AdGuard Home is
    # LAN-only (owner decision); its tunnel route was removed. 2026-11-17: Nexus
    # keeps its public route behind Access (owner decision).
    assert public_count == 33
    assert len(by_kind["DnsCheck"]) == public_count
    assert len(by_kind["TlsCheck"]) == public_count
    assert len(by_kind["HttpCheck"]) == public_count
    assert len(resources) == public_count * 3


def test_protected_http_checks_use_env_placeholders_not_secrets() -> None:
    resources = MODULE.generate_resources(_catalog())
    protected = [
        resource
        for resource in resources
        if resource["kind"] == "HttpCheck"
        and resource["metadata"]["labels"]["cloudflare_access"] == "required"
    ]

    # Explicit v2 policy includes a small set of public routes without Access.
    assert len(protected) == 28
    for resource in protected:
        headers = resource["spec"]["headers"]
        assert headers["CF-Access-Client-Id"] == "${CF_ACCESS_CLIENT_ID}"
        assert headers["CF-Access-Client-Secret"] == "${CF_ACCESS_CLIENT_SECRET}"

    serialized = yaml.safe_dump_all(resources)
    assert "client-secret-test" not in serialized
    assert "CF_ACCESS_CLIENT_SECRET=" not in serialized


def test_http_checks_use_string_assertions_for_common_error_pages() -> None:
    resources = MODULE.generate_resources(_catalog())
    http = next(resource for resource in resources if resource["kind"] == "HttpCheck")
    checks = http["spec"]["checks"]

    assert {"type": "duration", "operator": "lessThan", "value": "5s"} in checks
    assert {
        "type": "body",
        "operator": "notContains",
        "value": "Internal Server Error",
    } in checks
    assert {
        "type": "body",
        "operator": "notContains",
        "value": "Bad Gateway",
    } in checks


def test_prometheus_health_path_is_preserved() -> None:
    resources = MODULE.generate_resources(_catalog())
    prometheus = next(
        resource
        for resource in resources
        if resource["kind"] == "HttpCheck"
        and resource["metadata"]["labels"]["nabla_service_id"] == "prometheus"
    )
    assert prometheus["spec"]["url"].endswith("/-/ready")


def test_writer_emits_one_runner_compatible_yaml_per_resource(tmp_path: Path) -> None:
    resources = MODULE.generate_resources(_catalog())
    MODULE.write_resources(resources, tmp_path)

    paths = sorted(tmp_path.glob("*.yaml"))
    assert len(paths) == len(resources)
    sample = yaml.safe_load(paths[0].read_text(encoding="utf-8"))
    assert sample["apiVersion"] == "v1"
    assert sample["kind"] in {"DnsCheck", "TlsCheck", "HttpCheck"}
    assert sample["metadata"]["labels"]["observer"] == "fastapi-cloud"
    assert sample["metadata"]["labels"]["scope"] == "outside-in"
    assert sample["metadata"]["labels"]["source"] == "backstage-v2"
    assert sample["metadata"]["labels"]["nabla_entity_ref"]


def test_legacy_v1_catalog_is_not_a_synthetic_source() -> None:
    import pytest

    with pytest.raises(ValueError, match="requires Backstage catalog v2"):
        MODULE.generate_resources({"services": [{"id": "legacy", "external": True, "tunnelUrl": "https://legacy.albandrieu.com"}]})


def test_v2_monitors_have_unique_ids_and_explicit_revision() -> None:
    catalog = _catalog()
    assert catalog["catalogRevision"].startswith("sha256:")
    monitors = [r for r in MODULE.generate_resources(catalog) if r["kind"] == "HttpCheck"]
    ids = [r["metadata"]["labels"]["nabla_service_id"] for r in monitors]
    assert len(ids) == len(set(ids))
    assert all(r["metadata"]["labels"]["nabla_entity_ref"] for r in monitors)
