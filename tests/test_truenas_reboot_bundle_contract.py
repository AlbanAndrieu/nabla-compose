from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = ROOT / "scripts" / "truenas" / "materialize-reboot-bundle.sh"
REBOOT = ROOT / "scripts" / "truenas" / "reboot-homelab.sh"
ROADMAP = ROOT / "docs" / "roadmap.md"


def test_materializer_stages_before_atomic_activation() -> None:
    text = MATERIALIZER.read_text()
    assert "mktemp -d" in text
    assert 'mv "${STAGE}" "${FINAL}"' in text
    assert 'mv "${pointer_tmp}" "${BUNDLE_ROOT}/current"' in text
    assert "SOURCE_COMMIT" in text
    assert "SHA256SUMS" in text
    assert "sha256sum --quiet -c SHA256SUMS" in text
    assert "cmp -s" in text


def test_materializer_requires_resumable_reboot_script() -> None:
    text = MATERIALIZER.read_text()
    assert "--continue-prepare" in text
    assert "bash -n" in text
    assert "python3 -m py_compile" in text


def test_reboot_script_guards_same_boot_transactions_and_records_identity() -> None:
    text = REBOOT.read_text()
    assert 'for dir in "${STATE_ROOT}"/*-"${current}"' in text
    assert "same-boot reboot transaction already exists" in text
    assert "orchestrator-identity.txt" in text
    assert "prepare-history.log" in text
    assert "verify_bundle_integrity" in text


def test_reboot_script_keeps_workers_first_shutdown_order() -> None:
    text = REBOOT.read_text()
    assert "TALOS_NODES=(172.17.0.51 172.17.0.52 172.17.0.50)" in text
    assert "shutdown --wait" in text
    assert "shutdown --force" not in text


def test_roadmap_records_pre_reboot_orphan_resolution() -> None:
    text = ROADMAP.read_text()
    assert "successfully removed" in text
    assert "complete quiesce" in text
    assert "materialize-reboot-bundle.sh" in text
