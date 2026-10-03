from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts/truenas/collect-reboot-shutdown-evidence.sh"
MATERIALIZER = ROOT / "scripts/truenas/materialize-reboot-bundle.sh"


def test_reboot_shutdown_evidence_collector_is_read_only() -> None:
    text = COLLECTOR.read_text(encoding="utf-8")

    assert 'journalctl -b "${PREVIOUS_BOOT}"' in text
    assert "journalctl --list-boots" in text
    assert "systemctl --failed" in text
    assert "midclt call system.boot_id" in text
    assert "midclt call system.ready" in text
    assert "previous-boot-focus.txt" in text

    for forbidden in (
        "systemctl restart",
        "systemctl stop",
        "systemctl start",
        "midclt call system.reboot",
        "midclt call system.shutdown",
        "docker stop",
        "docker kill",
        "zfs destroy",
    ):
        assert forbidden not in text


def test_reboot_bundle_contains_shutdown_evidence_collector() -> None:
    text = MATERIALIZER.read_text(encoding="utf-8")
    assert "scripts/truenas/collect-reboot-shutdown-evidence.sh" in text
