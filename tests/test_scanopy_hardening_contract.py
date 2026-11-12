"""Contracts for the hardened Scanopy daemon and server."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def services() -> dict:
    compose = yaml.safe_load((ROOT / "apps/scanopy/compose.yml").read_text(encoding="utf-8"))
    return compose["services"]


def test_daemon_has_raw_sockets_but_no_privileged_mode_nor_docker_socket() -> None:
    daemon = services()["scanopy-daemon"]
    assert "privileged" not in daemon
    assert {"NET_RAW", "NET_ADMIN"} == set(daemon["cap_add"])
    assert "no-new-privileges:true" in daemon["security_opt"]
    assert not any("docker.sock" in volume for volume in daemon["volumes"])


def test_daemon_listens_on_docker0_only() -> None:
    daemon = services()["scanopy-daemon"]
    assert daemon["environment"]["SCANOPY_BIND_ADDRESS"] == "10.200.0.1"
    assert "http://10.200.0.1:60073/" in daemon["healthcheck"]["test"][1]


def test_registration_is_closed_unless_explicitly_opened() -> None:
    server = services()["scanopy"]
    assert server["environment"]["SCANOPY_DISABLE_REGISTRATION"] == "${SCANOPY_DISABLE_REGISTRATION:-true}"
