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
    mode="automatic", extra=False, monitor=False, business="low"
):
    folder = tmp_path / "apps" / "sample"
    folder.mkdir(parents=True, exist_ok=True)
    body = f'''name: sample
x-nabla:
  deploymentUnit:
    id: sample
    criticality: {criticality}
    businessCriticality: {business}
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


def test_unknown_business_criticality_blocks_auto_update(tmp_path):
    write_compose(tmp_path, business="null")
    assert "unsafe automatic upgrade" in policy.audit(tmp_path)[0][0]


def test_critical_cannot_auto_upgrade(tmp_path):
    write_compose(tmp_path, criticality="critical")
    assert "unsafe automatic upgrade" in policy.audit(tmp_path)[0][0]


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

def test_watchtower_config_enforces_manual_read_only_proxy(tmp_path):
    directory = tmp_path / "apps/watchtower"
    directory.mkdir(parents=True)
    (directory / "compose.yml").write_text("""name: watchtower
services:
  watchtower:
    image: nickfedor/watchtower:1.23.1
    environment:
      WATCHTOWER_LABEL_ENABLE: "true"
      WATCHTOWER_MONITOR_ONLY: "false"
      WATCHTOWER_NO_PULL: "true"
      DOCKER_HOST: tcp://docker-socket-proxy:2375
    volumes: [/var/run/docker.sock:/var/run/docker.sock:ro]
""")
    violations, _selected = policy.audit(tmp_path)
    assert any("unsafe WATCHTOWER_MONITOR_ONLY" in msg for msg in violations)
    assert any("manual-audit" in msg for msg in violations)
    assert any("socket/ports/privileged" in msg for msg in violations)


def test_post_enabled_docker_proxy_is_rejected(tmp_path):
    directory = tmp_path / "apps/watchtower"
    directory.mkdir(parents=True)
    (directory / "compose.yml").write_text("""name: watchtower
services:
  watchtower:
    image: nickfedor/watchtower:1.23.1
    profiles: [manual-audit]
    environment:
      WATCHTOWER_LABEL_ENABLE: "true"
      WATCHTOWER_MONITOR_ONLY: "true"
      WATCHTOWER_NO_PULL: "true"
      WATCHTOWER_LABEL_TAKE_PRECEDENCE: "false"
      WATCHTOWER_INCLUDE_STOPPED: "false"
      DOCKER_HOST: tcp://docker-socket-proxy:2375
    labels: {com.centurylinklabs.watchtower.enable: "false"}
""")
    (tmp_path / "docker-compose.yml").write_text("""services:
  docker-socket-proxy:
    environment:
      POST: 1
      IMAGES: 1
""")
    findings, _selected = policy.audit(tmp_path)
    assert any("POST must be disabled" in msg for msg in findings)
