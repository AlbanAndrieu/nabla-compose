"""Contracts for fixing Gatus generated config access without modifying SQLite."""

from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/repair-gatus-config-access.sh"
COMPOSE = ROOT / "apps/gatus/compose.yml"


def test_gatus_repair_script_is_bash_and_scoped() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'MODE="${1:---check}"' in source
    assert '[[ "${MODE}" == "--check" ]]' in source
    assert "getent group apps" in source
    assert "HostConfig.GroupAdd" in source
    assert 'chmod 0750 -- "${CONFIG_DIR}"' in source
    assert 'chmod 0640 -- "${CONFIG}"' in source
    assert "chgrp --" in source
    assert "gatus.db" not in source
    for forbidden in ("docker restart", "docker rm", "docker run", "app.start", "app.update", "chmod -R", "chmod 777", "sqlite3"):
        assert forbidden not in source


def test_gatus_compose_retains_group_read_without_world_exposure() -> None:
    service = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["gatus"]
    assert service["group_add"] == ["${GATUS_CONFIG_GID:-568}"]
    assert "./config:/config:ro" in service["volumes"]
    assert "/mnt/cpool/gatus:/data" in service["volumes"]
    assert "ALL" in service["cap_drop"]
