"""Cost-free CLI quality gates and bounded compact diagnostic rendering."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", [
    "scripts/truenas/finish-migrations-20261024.sh",
    "scripts/truenas/update-fastapi-sample.sh",
    "scripts/truenas/diagnose-influxdb.sh",
    "scripts/truenas/diagnose-stuck-apps.sh",
    "scripts/truenas/deploy-scrutiny.sh",
    "scripts/run-diagnostic.sh",
    "scripts/lib/diagnostic-ui.sh",
])
def test_bash_syntax_after_colored_compact_refactor(path):
    result = subprocess.run(["bash", "-n", str(ROOT / path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"{path}: {result.stderr}"


def test_stuck_app_summary_only_shows_actionable_redacted_names(tmp_path):
    fake = tmp_path / "diagnose-stuck-apps.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '\n=== APP gatus state=STOPPED ==='\n"
        "printf '%s\\n' 'reboot_context=expected-resume pre_reboot_state=RUNNING'\n"
        "printf '%s\\n' 'permission denied PRIVATE-TOKEN-DO-NOT-PRINT'\n"
        "printf '%s\\n' '\n=== APP tailscale state=STOPPED ==='\n"
        "printf '%s\\n' 'reboot_context=intentional-stopped pre_reboot_state=STOPPED'\n"
        "printf '%s\\n' 'SUMMARY problematic_apps=2 regressions=1 deferred=1'\n"
        "exit 1\n"
    )
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    env = os.environ.copy()
    env.update({"DIAGNOSTIC_LOG_DIR": str(root),
                "DIAG_COLOR": "never", "DIAG_ICONS": "never",
                "NO_COLOR": "1"})
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run-diagnostic.sh"), str(fake)],
        env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "gatus" in result.stdout
    assert "permissions" in result.stdout
    assert "DEFERRED" in result.stdout
    assert "tailscale: STOPPED" not in result.stdout
    assert "PRIVATE-TOKEN" not in result.stdout
    logs = list(root.glob("*.log"))
    assert len(logs) == 1
    assert (logs[0].stat().st_mode & 0o777) == 0o600


def test_gatus_existing_scoped_repair_is_preserved():
    script = (ROOT / "scripts/truenas/repair-gatus-config-access.sh").read_text()
    assert 'chmod 0640 -- "${CONFIG}"' in script
    assert 'chgrp -- "${EXPECTED_GID}"' in script
    assert 'gatus.db' not in script.split("chgrp --")[-1]


def test_scrutiny_stopped_reconciliation_requires_approval_and_preserves_data():
    script = (ROOT / "scripts/truenas/deploy-scrutiny.sh").read_text()
    assert 'SCRUTINY_CUTOVER_APPROVED' in script
    assert 'truenas_job_compact app.start "${SCRUTINY_APP_ID}"' in script
    assert '[[ "${RESET_SQLITE}" == "1" ]] || return 0' in script


def test_fastapi_image_identity_does_not_claim_build_sha():
    script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
    assert 'selected_image_id=' in script
    assert 'running_image_id=' in script
    assert 'build_revision=null' in script
