"""Offline contract tests for the observer Service Auth attachment script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cloudflare" / "attach-observer-service-auth.py"
SPEC = importlib.util.spec_from_file_location("attach_observer_service_auth", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

POLICY_ID = "11111111-1111-1111-1111-111111111111"


def test_targets_follow_catalog_access_contract() -> None:
    def route(host: str, **updates: object) -> dict:
        return {
            "visibility": "public",
            "protocol": "HTTPS",
            "gatewayRef": "resource:default/cloudflare-tunnel",
            "access": {"required": True},
            "hostnames": [host],
            **updates,
        }

    catalog = {
        "schemaVersion": 2,
        "model": "backstage",
        "entities": [
            {"x-nabla": {"exposure": [
                route("a.albandrieu.com"),
                route("i.albandrieu.com", visibility="lan"),
                route("direct.albandrieu.com", gatewayRef="resource:default/pfsense-haproxy"),
                route("n.albandrieu.com", access={"required": False}),
                route("foreign.example.com"),
                route("hello.int.albandrieu.com"),
            ]}},
        ],
    }
    assert MODULE.target_hosts(catalog) == ["a.albandrieu.com"]


def test_repository_catalog_targets_exclude_unexposed_services() -> None:
    catalog = json.loads((ROOT / "catalog/generated/entities.json").read_text())
    hosts = set(MODULE.target_hosts(catalog))

    assert hosts.isdisjoint({"litellm.albandrieu.com"})
    assert {"keycloak.albandrieu.com", "immich.albandrieu.com"} <= hosts
    assert not any(host.endswith(".int.albandrieu.com") for host in hosts)


def test_policy_must_be_service_auth_with_a_token() -> None:
    assert MODULE.validate_policy(None) == "policy not found"
    assert "non_identity" in MODULE.validate_policy({"decision": "allow", "include": []})
    assert MODULE.validate_policy({"decision": "non_identity", "include": [{"email": {}}]}) == (
        "policy does not include a service token"
    )
    assert MODULE.validate_policy({"decision": "non_identity", "include": [{"service_token": {"token_id": "x"}}]}) is None


def test_plan_skips_inline_policies_and_is_idempotent() -> None:
    reusable = {"policies": [{"id": "p1", "precedence": 1, "reusable": True}]}
    inline = {"policies": [{"id": "p1", "precedence": 1, "reusable": False}]}
    attached = {"policies": [{"id": POLICY_ID, "precedence": 1, "reusable": True}]}

    assert MODULE.plan_app(reusable, POLICY_ID)[0] == "attach"
    assert MODULE.plan_app(inline, POLICY_ID)[0] == "skip"
    assert MODULE.plan_app(attached, POLICY_ID)[0] == "ok"


def test_update_body_keeps_settings_and_appends_unique_precedence() -> None:
    app = {
        "id": "app-1",
        "aud": "secret-ish-tag",
        "created_at": "x",
        "updated_at": "y",
        "name": "Grafana",
        "domain": "grafana.albandrieu.com",
        "type": "self_hosted",
        "session_duration": "24h",
        "policies": [
            {"id": "p2", "precedence": 2, "reusable": True, "name": "b"},
            {"id": "p1", "precedence": 1, "reusable": True, "name": "a"},
        ],
    }

    body = MODULE.build_update_body(app, POLICY_ID)

    assert {"id", "aud", "created_at", "updated_at"}.isdisjoint(body)
    assert body["domain"] == "grafana.albandrieu.com" and body["session_duration"] == "24h"
    assert body["policies"] == [
        {"id": "p1", "precedence": 1},
        {"id": "p2", "precedence": 2},
        {"id": POLICY_ID, "precedence": 3},
    ]


def test_app_hosts_ignore_path_scoped_destinations() -> None:
    app = {
        "domain": "n8n.albandrieu.com/rest/oauth2-credential/callback*",
        "destinations": [{"type": "public", "uri": "grafana.albandrieu.com"}],
    }

    assert MODULE.app_hosts(app) == {"grafana.albandrieu.com"}
