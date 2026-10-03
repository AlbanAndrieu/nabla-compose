from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/restore-app-set.sh"
POST_PRA_CORE = ROOT / "config/truenas/restore-post-pra-core-apps.txt"


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
    assert "ensure-docker-socket-proxy-intranet.sh" in text
    assert "verify-pihole-dns-sync.sh" in text
    assert "PREPARE %s storage ownership" in text
    assert "PREPARE %s shared intranet attachment" in text
    assert "VERIFY %s DNS sync dependency contract" in text
    assert "midclt call -j app.start" in text

    assert "systemctl restart docker" not in text
    assert "systemctl restart containerd" not in text
    assert "docker kill" not in text
    assert "pkill" not in text


def test_post_pra_core_restore_set_is_catalog_driven_and_excludes_runtime_drift() -> None:
    active = [
        line.strip()
        for line in POST_PRA_CORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert set(active) == {"vaultwarden"}
    for native_or_pending in (
        "adguard-home", "grafana", "prometheus", "uptime-kuma", "autokuma"
    ):
        assert native_or_pending not in active
