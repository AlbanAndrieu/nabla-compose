"""Offline restart planning is read-only, ordered and redacted."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/truenas/plan-catalog-v2-restart.py"
SPEC = importlib.util.spec_from_file_location("v2restart", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_sanitized_snapshot_only_id_and_state() -> None:
    with pytest.raises(ValueError, match="ONLY id and state"):
        mod.stable_app_states([{"id": "postgres", "state": "RUNNING", "credentials": "secret"}])
    with pytest.raises(ValueError, match="duplicate"):
        mod.stable_app_states([{"id": "postgres", "state": "RUNNING"},
                               {"id": "postgres", "state": "STOPPED"}])


def test_topology_order_and_cycle_detection() -> None:
    assert mod.topo_waves({"postgres", "scanopy"}, {("postgres", "scanopy")}) == [
        ["postgres"], ["scanopy"]
    ]
    with pytest.raises(ValueError, match="cycle"):
        mod.topo_waves({"a", "b"}, {("a", "b"), ("b", "a")})


def test_two_stages_and_no_secret_values() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "apps/postgres").mkdir(parents=True)
        (root / "apps/scanopy").mkdir(parents=True)
        (root / "catalog").mkdir()
        (root / "config/secrets").mkdir(parents=True)
        (root / "catalog/catalog-info.yaml").write_text(
            "kind: Resource\nmetadata:\n  name: postgres\n---\n"
            "kind: Component\nmetadata:\n  name: scanopy\n"
            "spec:\n  dependsOn: [resource:default/postgres]\n")
        (root / "apps/postgres/compose.yml").write_text(
            "services:\n  postgres:\n    labels:\n"
            "      com.albandrieu.nabla.entity-ref: resource:default/postgres\n")
        (root / "apps/scanopy/compose.yml").write_text(
            "services:\n  scanopy:\n    labels:\n"
            "      com.albandrieu.nabla.entity-ref: component:default/scanopy\n"
            "    env_file: [/mnt/cpool/secrets/runtime/scanopy/.env.secrets]\n")
        (root / "config/secrets/manifest.json").write_text(json.dumps({
            "items": [{"app": "scanopy", "item": "nabla/prod/scanopy"}]
        }))
        report = mod.build_plan(root, [
            {"id": "postgres", "state": "RUNNING"},
            {"id": "scanopy", "state": "STOPPED"},
        ])
    rows = {app["appId"]: app for app in report["apps"]}
    assert rows["postgres"]["stage"] == "running-first"
    assert rows["postgres"]["action"] == "redeploy"
    assert rows["scanopy"]["stage"] == "remaining"
    assert rows["scanopy"]["action"] == "start"
    assert rows["scanopy"]["dependencies"] == ["postgres"]
    assert rows["scanopy"]["vaultwardenItem"] == "nabla/prod/scanopy"
    assert rows["scanopy"]["runtimeSecretFiles"][0]["status"] == "not-checked"
    assert "secret-value" not in json.dumps(report)
    assert report["readOnly"] is True


def test_running_first_holds_dependencies_and_missing_runtime_secrets() -> None:
    # Dependency and path checks are independent; a RUNNING app with a missing
    # prerequisite is never eligible for an automatic redeploy.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for app in ("mongo", "worker"):
            (root / "apps" / app).mkdir(parents=True)
        (root / "catalog").mkdir()
        (root / "config/secrets").mkdir(parents=True)
        (root / "config/secrets/manifest.json").write_text(json.dumps({"items": []}))
        (root / "catalog/catalog-info.yaml").write_text(
            "kind: Resource\nmetadata:\n  name: mongo\n---\n"
            "kind: Component\nmetadata:\n  name: worker\n"
            "spec:\n  dependsOn: [resource:default/mongo]\n"
        )
        (root / "apps/mongo/compose.yml").write_text(
            "services:\n  mongo:\n    labels:\n"
            "      com.albandrieu.nabla.entity-ref: resource:default/mongo\n"
        )
        (root / "apps/worker/compose.yml").write_text(
            "services:\n  worker:\n    labels:\n"
            "      com.albandrieu.nabla.entity-ref: component:default/worker\n"
            "    env_file: [/mnt/cpool/secrets/runtime/worker/.env.secrets]\n"
        )
        report = mod.build_plan(root, [
            {"id": "mongo", "state": "STOPPED"},
            {"id": "worker", "state": "RUNNING"},
        ], check_host_secrets=True)
    worker = next(app for app in report["apps"] if app["appId"] == "worker")
    assert worker["action"] == "hold"
    assert set(worker["blockers"]) == {
        "dependency-not-running", "runtime-secrets-not-ready"
    }
    assert worker["vaultwardenValidation"] == "not-checked"
