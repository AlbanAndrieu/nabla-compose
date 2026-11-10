"""Hermetic contract for scripts/truenas/verify-service-observability.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_obs", ROOT / "scripts/truenas/verify-service-observability.py")
assert SPEC is not None and SPEC.loader is not None
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_gatus_key_matches_gatus_normalisation() -> None:
    assert verify._gatus_key({"group": "productivity", "name": "Joplin Server"}) == "productivity_joplin-server"
    assert verify._gatus_key({"group": "data", "name": "Dependency-Track API"}) == "data_dependency-track-api"


def test_every_default_service_is_declared_and_probed_by_gatus() -> None:
    catalog = verify._services()
    endpoints = verify._gatus_endpoints()
    missing_catalog = [s for s in verify.DEFAULT_SERVICES if s not in catalog]
    assert missing_catalog == []
    # Gatus emits only operational-state=active services; the others must be
    # explained by their Backstage label, never silently missing.
    for service in verify.DEFAULT_SERVICES:
        if service not in endpoints:
            result = verify.check_gatus(None, "http://gatus", service)
            assert result["state"] == "fail" and "operational-state" in result["reason"] or "no Gatus endpoint" in result["reason"]


def test_all_three_facts_must_hold(monkeypatch) -> None:
    def fake_get(url: str, timeout: float = 0) -> tuple[int, bytes]:
        if "/api/v1/endpoints/" in url:
            return 200, json.dumps({"results": [{"success": True, "timestamp": "t"}]}).encode()
        if "gatus_results_endpoint_success" in url:
            return 200, json.dumps({"status": "success", "data": {"result": [{"value": [0, "1"]}]}}).encode()
        if "up%7Bjob" in url:
            return 200, json.dumps({"status": "success", "data": {"result": [{"value": [0, "0"]}]}}).encode()
        return 200, b""

    monkeypatch.setattr(verify, "_get", fake_get)
    jobs = {"netbox"}
    prometheus = verify.check_prometheus("netbox", jobs, "http://prom")
    assert prometheus["state"] == "fail" and prometheus["up"] == ["0"]
    assert verify.check_prometheus("joplin", jobs, "http://prom")["state"] == "ok"
    gatus = verify.check_gatus({"group": "productivity", "name": "Joplin Server"}, "http://gatus")
    assert gatus["state"] == "ok"


def test_script_is_read_only() -> None:
    source = (ROOT / "scripts/truenas/verify-service-observability.py").read_text(encoding="utf-8")
    for forbidden in ("midclt", "docker ", "subprocess", "method=\"POST\"", "app.start"):
        assert forbidden not in source
