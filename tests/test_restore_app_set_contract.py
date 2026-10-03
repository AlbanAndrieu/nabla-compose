from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/restore-app-set.sh"


def test_restore_app_set_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--apps-file" in text
    assert "plan-app-lifecycle-order.py" in text
    assert "verify-app-runtime-health.sh" in text
    assert "--states __NONE__" in text
    assert "start_waves" in text
    assert "refusing blind restart" in text
    assert "dependency barrier" in text
    assert "NABLA_APP_START_WAIT_OVERRIDES" in text
    assert "repair-opensearch-security-permissions.sh" in text
    assert "PREPARE %s storage ownership" in text
    assert "midclt call -j app.start" in text

    assert "systemctl restart docker" not in text
    assert "systemctl restart containerd" not in text
    assert "docker kill" not in text
    assert "pkill" not in text
