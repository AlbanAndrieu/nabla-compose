"""Contracts for repository-managed Docling and Joplin services."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_compose(relative: str) -> dict:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def test_docling_is_private_versioned_and_openrag_addressable() -> None:
    compose = load_compose("apps/docling/compose.yml")
    service = compose["services"]["docling"]
    metadata = service["x-nabla"]

    assert service["image"].endswith("${DOCLING_VERSION:-v1.32.0}")
    assert "172.17.0.24:5001:5001" in service["ports"]
    assert set(service["networks"]) == {"intranet", "traefik_network"}
    assert metadata["internalUrl"] == "http://docling:5001"
    assert metadata["url"] == "https://docling.int.albandrieu.com"
    assert metadata["monitoring"]["target"].endswith(":5001/ready")

    relation = compose["x-nabla"]["relations"][0]
    assert relation == {
        "source": "openrag-backend",
        "target": "docling",
        "type": "consumesApi",
        "strength": "required",
        "description": "OpenRAG sends document conversion requests to the repository-managed Docling Serve API.",
        "evidence": ["apps/openrag/compose.yml:DOCLING_SERVE_URL"],
    }


def test_joplin_uses_shared_postgres_and_private_ingress() -> None:
    compose = load_compose("apps/joplin/compose.yml")
    service = compose["services"]["joplin"]
    metadata = service["x-nabla"]

    assert service["image"] == "joplin/server:${JOPLIN_VERSION:-3.7.18}"
    assert service["environment"]["POSTGRES_HOST"] == "172.17.0.24"
    assert service["environment"]["POSTGRES_PORT"] == "5432"
    assert service["environment"]["POSTGRES_DATABASE"] == "joplin"
    assert service["environment"]["POSTGRES_USER"] == "joplin"
    assert "/mnt/cpool/joplin/.env.secrets" in service["env_file"]
    assert "POSTGRES_PASSWORD" not in service["environment"]
    assert metadata["url"] == "https://joplin.int.albandrieu.com"
    assert metadata["monitoring"]["target"].endswith(":22300/api/ping")

    relations = {(item["target"], item["type"]) for item in metadata["relations"]}
    assert ("postgresql", "dependsOn") in relations
    assert ("traefik", "exposedBy") in relations
