"""Offline regression tests for opt-in and unit-safe Watchtower policies."""
from __future__ import annotations

import importlib.util
import pathlib

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts/security/check-watchtower-unit-policy.py"
)
spec = importlib.util.spec_from_file_location("watchtower_policy", SCRIPT)
assert spec is not None and spec.loader is not None
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def write_compose(
    tmp_path, *, criticality="low", stateful=False,
    mode="automatic", extra=False, monitor=False
):
    folder = tmp_path / "apps" / "sample"
    folder.mkdir(parents=True, exist_ok=True)
    body = f'''name: sample
x-nabla:
  deploymentUnit:
    id: sample
    criticality: {criticality}
    stateful: {str(stateful).lower()}
    upgradePolicy: {mode}
services:
  web:
    image: busybox
    labels:
      com.centurylinklabs.watchtower.enable: "true"
      com.centurylinklabs.watchtower.monitor-only: "{str(monitor).lower()}"
'''
    if extra:
        body += '  job:\n    image: busybox\n'
    (folder / "compose.yml").write_text(body)


def test_low_stateless_single_can_opt_in(tmp_path):
    write_compose(tmp_path)
    findings, selected = policy.audit(tmp_path)
    assert not findings
    assert selected == ["apps/sample/compose.yml:web [automatic]"]


def test_critical_cannot_auto_upgrade(tmp_path):
    write_compose(tmp_path, criticality="critical")
    assert "automatic upgrade requires" in policy.audit(tmp_path)[0][0]


def test_stateful_cannot_auto_upgrade(tmp_path):
    write_compose(tmp_path, stateful=True)
    assert policy.audit(tmp_path)[0]


def test_multi_container_cannot_auto_upgrade(tmp_path):
    write_compose(tmp_path, extra=True)
    assert policy.audit(tmp_path)[0]


def test_multi_container_monitor_only_allowed(tmp_path):
    write_compose(
        tmp_path, extra=True, criticality="medium",
        stateful=True, mode="observe", monitor=True
    )
    assert not policy.audit(tmp_path)[0]


def test_excluded_unit_cannot_opt_in(tmp_path):
    write_compose(tmp_path, mode="excluded", monitor=True)
    assert policy.audit(tmp_path)[0]


def test_unlabeled_containers_are_not_selected(tmp_path):
    write_compose(tmp_path)
    p = tmp_path / "apps/sample/compose.yml"
    p.write_text(
        p.read_text().replace(
            'com.centurylinklabs.watchtower.enable: "true"',
            'com.centurylinklabs.watchtower.enable: "false"',
        )
    )
    assert policy.audit(tmp_path) == ([], [])


def test_repository_policy_is_consistent():
    root = pathlib.Path(__file__).resolve().parents[1]
    findings, selected = policy.audit(root)
    assert not findings
    assert any("homarr" in x and "[observe]" in x for x in selected)
    assert not any("garage" in x for x in selected)
