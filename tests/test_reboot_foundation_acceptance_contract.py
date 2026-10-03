from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECONCILER = ROOT / "scripts/truenas/reconcile-reboot-resume.sh"
MATERIALIZER = ROOT / "scripts/truenas/materialize-reboot-bundle.sh"
REBOOT = ROOT / "scripts/truenas/reboot-homelab.sh"


def test_reboot_resume_reuses_foundation_recovery_contracts() -> None:
    text = RECONCILER.read_text(encoding="utf-8")

    assert "repair-opensearch-security-permissions.sh" in text
    assert "ensure-docker-socket-proxy-intranet.sh" in text
    assert "verify-pihole-dns-sync.sh" in text
    assert "prepare_app_storage" in text
    assert "prepare_app_runtime" in text
    assert "verify_app_contracts" in text
    assert 'prepare_app_storage "${app}"' in text
    assert 'prepare_app_runtime "${app}"' in text
    assert 'verify_app_contracts "${app}"' in text

    assert "systemctl restart docker" not in text
    assert "systemctl restart containerd" not in text
    assert "docker kill" not in text


def test_immutable_reboot_bundle_contains_foundation_helpers() -> None:
    text = MATERIALIZER.read_text(encoding="utf-8")

    for helper in (
        "repair-opensearch-security-permissions.sh",
        "ensure-docker-socket-proxy-intranet.sh",
        "verify-pihole-dns-sync.sh",
    ):
        assert f"scripts/truenas/{helper}" in text
        assert helper in text


def test_strict_reboot_verify_delegates_to_specialized_reconciler() -> None:
    text = REBOOT.read_text(encoding="utf-8")

    assert 'bash "${RESUME_RECONCILER}" --check' in text
    assert "saved Apps failed final RUNNING acceptance" in text
