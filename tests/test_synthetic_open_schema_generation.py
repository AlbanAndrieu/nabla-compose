"""Contract tests for generated outside-in Synthetic Open Schema resources."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate-synthetic-open-schema.py"
CATALOG = ROOT / "catalog" / "homelab-services.json"

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
        for service in _catalog()["services"]
        if isinstance(service, dict)
    )
    assert public_count == 26
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

    assert len(protected) == 25
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
