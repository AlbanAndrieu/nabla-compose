from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_workstation_entrypoint_includes_monitoring_fragment() -> None:
    entrypoint = read("docker-compose-albandrieu.yml")

    assert "- path: compose.monitoring.yml" in entrypoint


def test_workstation_scrutiny_collector_is_declaratively_managed() -> None:
    compose = read("compose.monitoring.yml")

    assert "scrutiny-collector:" in compose
    assert "ghcr.io/analogj/scrutiny:v0.9.3-collector" in compose
    assert "container_name: scrutiny" in compose
    assert "COLLECTOR_API_ENDPOINT: http://172.17.0.24:31054/" in compose
    assert "COLLECTOR_HOST_ID: albandrieu" in compose
    assert "/run/udev:/run/udev:ro" in compose
    assert "/dev/sda:/dev/sda" in compose
    assert "/dev/sdb:/dev/sdb" in compose
    assert "/dev/sdc:/dev/sdc" in compose
    assert "master-collector" not in compose


def test_summary_checks_allow_one_transient_busy_timeout() -> None:
    workstation = read(
        "scripts/observability/verify-scrutiny-workstation-collector.sh"
    )
    truenas = read("scripts/truenas/verify-scrutiny-collectors.sh")

    assert "SCRUTINY_WORKSTATION_SUMMARY_MAX_TIME_SECONDS" in workstation
    assert "transient Scrutiny /api/summary failure" in workstation
    assert "recovered after" in workstation

    assert "SCRUTINY_SUMMARY_ATTEMPTS" in truenas
    assert "SCRUTINY_SUMMARY_MAX_TIME_SECONDS" in truenas
    assert "SCRUTINY_SUMMARY_RETRY_DELAY_SECONDS" in truenas
    assert "Scrutiny /api/summary recovered after" in truenas
    assert "did not converge" in truenas


def test_scrutiny_verifiers_remain_executable_valid_bash() -> None:
    paths = [
        ROOT / "scripts/observability/verify-scrutiny-workstation-collector.sh",
        ROOT / "scripts/truenas/verify-scrutiny-collectors.sh",
    ]

    for path in paths:
        assert path.stat().st_mode & stat.S_IXUSR
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
