"""Contracts for the planned repository-owned OWASP OpenCRE service."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "opencre" / "compose.yml"
README = ROOT / "apps" / "opencre" / "README.md"
CATALOG = ROOT / "apps" / "opencre" / "catalog-info.yaml"
STORAGE = ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh"


def test_opencre_compose_is_internal_persistent_and_fail_safe() -> None:
    payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = payload["services"]["opencre"]

    assert "ghcr.io/owasp/opencre/opencre:latest" in service["image"]
    assert service["x-nabla"]["id"] == "opencre"
    assert service["x-nabla"]["status"] == "planned"
    assert service["x-nabla"]["runtime"]["provider"] == "truenas-app"

    port = service["ports"][0]
    assert port["target"] == 5000
    assert port["published"] == "31089"
    assert port["host_ip"] == "172.17.0.24"

    env = service["environment"]
    assert env["PROD_DATABASE_URL"] == "sqlite:////db/db.sqlite"
    assert env["CRE_ENABLE_HEALTH"] == "1"
    assert env["CRE_ALLOW_IMPORT"] == "0"
    assert env["CRE_ENABLE_MYOPENCRE"] == "0"
    assert env["CRE_ENABLE_LOGIN"] == "0"

    assert "/mnt/cpool/opencre/db:/db" in service["volumes"]
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "healthcheck" in service
    assert service["x-nabla"]["relations"][0]["target"] == "dsomm"


def test_opencre_docs_keep_floating_image_blocked_from_activation() -> None:
    text = README.read_text(encoding="utf-8")
    assert "status: planned" in text
    assert "immutable version/digest" in text
    assert "CRE_ALLOW_IMPORT=0" in text
    assert "Neo4j/gap-analysis" in text
    assert "DSOMM remains" in text


def test_storage_bootstrap_discovers_opencre_bind_mount_without_special_case() -> None:
    script = STORAGE.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "git ls-files 'apps/*/compose.yml'" in script
    assert "/mnt/cpool/opencre/db:/db" in compose
    assert 'declared_paths["opencre"]' not in script


def test_backstage_component_is_planned_security_tool() -> None:
    docs = list(yaml.safe_load_all(CATALOG.read_text(encoding="utf-8")))
    component = docs[0]
    assert component["metadata"]["name"] == "opencre"
    assert component["metadata"]["labels"]["albandrieu.com/operational-state"] == "planned"
    assert component["spec"]["type"] == "security-tool"
    assert "component:default/dsomm" in component["spec"]["dependsOn"]
