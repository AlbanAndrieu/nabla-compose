"""sync_vaultwarden_service_logins.py only adds URIs and fills empty login fields."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/secrets"))

import sync_vaultwarden_service_logins as sync  # noqa: E402

# Test data built at run time: no literal that looks like a credential.
VALUE, KEPT, OTHER = ("-".join(("fake", word)) for word in ("value", "kept", "other"))

APPS = [
    {"id": "dependency-track", "href": "http://172.17.0.24:31084", "sourcePath": "apps/dependency-track/compose.yml"},
    {"id": "dependency-track-api", "href": None, "sourcePath": "apps/dependency-track/compose.yml"},
    {"id": "scrutiny", "href": "https://scrutiny.int.albandrieu.com", "sourcePath": "apps/scrutiny/compose.yml"},
]


def test_fills_placeholder_login_from_the_field_and_adds_the_ui_url():
    item = {"type": 1, "login": {"username": "homelab:dependency-track", "password": None, "uris": None},
            "fields": [{"name": "DT_ADMIN_PASSWORD", "value": VALUE, "type": 1}]}
    out, changes = sync.complete(item, "dependency-track", sync.ui_urls(APPS, "dependency-track"))
    assert changes == ["uri+1", "username", "password"]
    assert out["login"] == {"username": "admin", "password": VALUE,
                            "uris": [{"match": None, "uri": "http://172.17.0.24:31084"}]}
    assert item["login"]["password"] is None  # the input item is left untouched


def test_never_overwrites_an_existing_login_or_uri():
    item = {"type": 1, "login": {"username": "me", "password": KEPT,
                                 "uris": [{"match": None, "uri": "http://172.17.0.24:31084"}]},
            "fields": [{"name": "DT_ADMIN_PASSWORD", "value": OTHER, "type": 1}]}
    out, changes = sync.complete(item, "dependency-track", sync.ui_urls(APPS, "dependency-track"))
    assert changes == []
    assert out["login"]["username"] == "me" and out["login"]["password"] == KEPT


def test_service_without_ui_login_only_gains_its_url():
    item = {"type": 1, "login": {"username": "homelab:scrutiny", "password": ""}, "fields": []}
    out, changes = sync.complete(item, "scrutiny", sync.ui_urls(APPS, "scrutiny"))
    assert changes == ["uri+1"]
    assert out["login"]["username"] == "homelab:scrutiny"


def test_reports_a_missing_password_field_without_writing_it():
    item = {"type": 1, "login": {"username": "homelab:grafana"}, "fields": []}
    _, changes = sync.complete(item, "grafana", [])
    assert changes == ["username", "no GRAFANA_ADMIN_PASSWORD field"]
