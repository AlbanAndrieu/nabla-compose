from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-stuck-apps.sh"


def test_stuck_app_diagnostic_is_read_only_and_bounded() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--check" in text
    assert "NABLA_STUCK_APP_QUERY_TIMEOUT_SECONDS" in text
    assert "core.get_jobs" in text
    assert "docker ps -a" in text
    assert "docker inspect" in text
    assert "docker logs --tail" in text
    assert "diagnose-sentry.sh --check" in text
    assert "diagnose-wazuh.sh --check" in text

    for forbidden in (
        "app.start",
        "app.stop",
        "app.update",
        "app.redeploy",
        "docker restart",
        "docker rm",
        "docker image prune",
        "docker system prune",
    ):
        assert forbidden not in text

    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
