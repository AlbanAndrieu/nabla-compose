"""Offline Kubernetes/Talos upgrade preflight contracts."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
tools = runpy.run_path(str(ROOT / "scripts/talos/preflight-supported-upgrade.py"))
validate_nodes = tools["validate_nodes"]
preflight = tools["main"]


def nodes(version="v1.36.3", ready=True):
    return {"items": [
        {"metadata": {"name": name}, "status": {
            "nodeInfo": {"kubeletVersion": version},
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        }}
        for name in ("control-plane", "worker-1", "worker-2")
    ]}


def test_healthy_cluster_offline():
    assert validate_nodes(nodes()) == []
    assert validate_nodes(nodes("v1.37.1")) == []


@pytest.mark.parametrize("quantity", [0, 1, 2, 4])
def test_exact_three_nodes_required(quantity):
    assert any("expected 3 nodes" in msg
               for msg in validate_nodes({"items": nodes()["items"][:quantity]}))


def test_not_ready_and_pressure_are_blocking():
    data = nodes(ready=False)
    data["items"][0]["status"]["conditions"].append(
        {"type": "DiskPressure", "status": "True"})
    findings = validate_nodes(data)
    assert any("NotReady" in msg for msg in findings)
    assert any("DiskPressure" in msg for msg in findings)


def test_unknown_kubelet_version_fails():
    assert any("kubelet version unavailable" in msg
               for msg in validate_nodes(nodes(version="")))


@pytest.mark.parametrize("payload", [[], {}, {"items": None}, None])
def test_malformed_node_payload_fails_closed(payload):
    assert validate_nodes(payload)


def test_no_cluster_calls_in_offline_preflight(tmp_path, monkeypatch, capsys):
    data = tmp_path / "nodes.json"
    data.write_text(json.dumps(nodes()), encoding="utf-8")
    monkeypatch.setitem(preflight.__globals__, "call", lambda *a, **k:
                        pytest.fail("no subprocess calls permitted"))
    assert preflight(["--nodes-json", str(data)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["readOnly"] is True
    assert output["runtimeUpgradePerformed"] is False
    assert output["etcdSnapshotVerified"] is False
    assert output["csiSmokeVerified"] is False
    assert output["targetTalos"] == "v1.14.4"
    assert output["targetKubernetes"] == "v1.37.1"
