"""Contract tests for the read-only, declarative deployment-unit projection."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/security/audit-deployment-units.py"
)
spec = importlib.util.spec_from_file_location("deployment_units", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def compose(tmp_path: Path, name: str, contents: str) -> None:
    directory = tmp_path / "apps" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "compose.yml").write_text(contents, encoding="utf-8")


GARAGE = """name: garage
x-nabla:
  deploymentUnit:
    id: garage
    criticality: high
    stateful: true
    upgradePolicy: controlled
    probeOrder: [garage, garage-admin, garage-webui]
  nodes:
    - id: garage-admin
      criticality: high
  relations:
    - source: garage-admin
      target: garage
      type: partOf
services:
  garage:
    image: garage:local
    x-nabla:
      id: garage
  webui:
    image: webui:local
    depends_on: [garage]
    x-nabla:
      id: garage-webui
"""


def test_garage_is_one_unit_three_endpoints_two_containers(tmp_path):
    compose(tmp_path, "garage", GARAGE)
    report = module.collect(tmp_path)
    (unit,) = report["units"]
    assert unit["deploymentUnitId"] == "truenas:garage"
    assert unit["endpointIds"] == ["garage", "garage-admin", "garage-webui"]
    assert len(unit["containers"]) == 2
    assert unit["containers"][1]["dependsOn"] == ["garage"]
    assert unit["operationalCriticality"] == "high"
    assert unit["businessCriticality"] is None
    assert not unit["watchtowerAutoEligible"]


def test_stateless_low_is_not_automatically_safe_without_bia(tmp_path):
    compose(
        tmp_path, "tool",
        """name: tool
x-nabla:
  deploymentUnit:
    id: tool
    criticality: low
    stateful: false
    upgradePolicy: automatic
services:
  tool:
    image: tool:latest
    x-nabla: {id: tool}
""",
    )
    assert module.collect(tmp_path)["units"][0]["watchtowerAutoEligible"] is False


def test_low_business_and_operations_allow_single_unit_candidate(tmp_path):
    compose(
        tmp_path, "tool",
        """name: tool
x-nabla:
  deploymentUnit:
    id: tool
    criticality: low
    businessCriticality: low
    stateful: false
    upgradePolicy: automatic
services:
  tool:
    image: tool:latest
    x-nabla: {id: tool}
""",
    )
    (unit,) = module.collect(tmp_path)["units"]
    assert unit["watchtowerAutoCandidate"] is True
    assert unit["watchtowerAutoEligible"] is False


@pytest.mark.parametrize("unit", [
    "probeOrder: [garage, garage-webui]",
    "probeOrder: [garage, garage-admin, garage-webui, garage]",
])
def test_probe_order_fails_closed(tmp_path, unit):
    compose(tmp_path, "garage", GARAGE.replace(
        "probeOrder: [garage, garage-admin, garage-webui]", unit,
    ))
    with pytest.raises(ValueError, match="probeOrder"):
        module.collect(tmp_path)


def test_dependency_graph_orders_garage_without_manual_order(tmp_path):
    compose(
        tmp_path, "garage",
        GARAGE.replace(
            "    probeOrder: [garage, garage-admin, garage-webui]\\n", ""
        ),
    )
    (unit,) = module.collect(tmp_path)["units"]
    assert unit["endpointIds"][0] == "garage"
    assert unit["probePlan"]["maxConcurrentPerUnit"] == 1
    assert unit["probePlan"]["execution"] == "serialized-on-demand"


def test_invalid_explicit_order_cannot_reverse_dependency(tmp_path):
    compose(
        tmp_path, "garage",
        GARAGE.replace(
            "[garage, garage-admin, garage-webui]",
            "[garage-webui, garage, garage-admin]",
        ),
    )
    with pytest.raises(ValueError, match="probeOrder violates"):
        module.collect(tmp_path)


def test_dependency_cycle_is_rejected():
    nodes = ["a", "b"]
    containers = [
        {"composeService": "a", "endpointId": "a", "dependsOn": ["b"]},
        {"composeService": "b", "endpointId": "b", "dependsOn": ["a"]},
    ]
    with pytest.raises(ValueError, match="cycle"):
        module.infer_probe_order(nodes, containers, [])


def test_unresolved_compose_dependency_rejected(tmp_path):
    compose(tmp_path, "garage", GARAGE.replace(
        "depends_on: [garage]", "depends_on: [not-there]",
    ))
    with pytest.raises(ValueError, match="unresolved"):
        module.collect(tmp_path)


def test_duplicate_deployment_unit_rejected(tmp_path):
    compose(tmp_path, "garage", GARAGE)
    compose(tmp_path, "replica", GARAGE)
    with pytest.raises(ValueError, match="duplicate deployment unit"):
        module.collect(tmp_path)


def test_without_unit_metadata_is_unclassified_and_excluded(tmp_path):
    compose(tmp_path, "legacy", """name: legacy
services:
  legacy:
    image: busybox
""")
    (unit,) = module.collect(tmp_path)["units"]
    assert unit["operationalCriticality"] is None
    assert unit["businessCriticality"] is None
    assert unit["upgradePolicy"] == "excluded"
    assert not unit["watchtowerAutoEligible"]


def test_deterministic_output(tmp_path):
    compose(tmp_path, "garage", GARAGE)
    assert module.collect(tmp_path) == module.collect(tmp_path)


def test_repo_garage_and_homarr_contracts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in ("garage", "homarr"):
        compose(
            tmp_path, name,
            (root / f"apps/{name}/compose.yml").read_text(encoding="utf-8"),
        )
    items = {
        item["deploymentUnitId"]: item
        for item in module.collect(tmp_path)["units"]
    }
    garage = items["truenas:garage"]
    assert garage["endpointIds"] == ["garage", "garage-admin", "garage-webui"]
    assert not garage["watchtowerAutoEligible"]
    assert items["truenas:homarr"]["upgradePolicy"] == "observe"
    assert not items["truenas:homarr"]["watchtowerAutoEligible"]
