from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "scripts/truenas/ensure-docker-socket-proxy-intranet.sh"
PIHOLE = ROOT / "scripts/truenas/verify-pihole-dns-sync.sh"


def test_docker_socket_proxy_intranet_recovery_contract() -> None:
    text = PROXY.read_text(encoding="utf-8")

    assert "midclt call app.query" in text
    assert "active_workloads.container_details" in text
    assert "docker network connect --alias" in text
    assert "docker-socket-proxy" in text
    assert "intranet" in text
    assert "runtime-scoped" in text

    assert "systemctl restart docker" not in text
    assert "systemctl restart containerd" not in text
    assert "docker network rm" not in text


def test_pihole_dns_sync_acceptance_contract() -> None:
    text = PIHOLE.read_text(encoding="utf-8")

    # DNS resolution is delegated to the shared container probe helper,
    # which runs bounded `docker exec ... getent hosts` internally.
    assert 'source "${SCRIPT_DIR}/../lib/probe.sh"' in text
    assert 'probe_container_dns_success "${SYNC_CONTAINER}" "${PROXY_ALIAS}" 3' in text
    assert 'probe_container_dns_records "${SYNC_CONTAINER}" "${PROXY_ALIAS}" 3' in text
    probe = (ROOT / "scripts/lib/probe.sh").read_text(encoding="utf-8")
    assert 'docker exec "${container}" getent hosts "${hostname}"' in probe
    assert "Initial sync done" in text
    assert "api_seats_exceeded" in text
    assert "failed to connect to the docker API" in text
    assert "FTLCONF_webserver_api_max_sessions=" in text
    assert "webserver.api.max_sessions" in text
    assert "NABLA_PIHOLE_EXPECTED_MAX_SESSIONS:-16" in text

    assert "FTLCONF_webserver_api_max_sessions: 32" not in text
    assert "systemctl restart docker" not in text
    assert "docker kill" not in text
