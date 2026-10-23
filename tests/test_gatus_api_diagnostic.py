"""Offline, redaction-safe Gatus API status diagnostic regression tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-gatus.sh"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq unavailable")
@pytest.mark.parametrize("entries,expected,exit_code", [
    ([{"results": [{"success": False}, {"success": True}]},
      {"results": [{"success": False}]}],
     "monitors=2 up=1 down=1 pending=0 unknown=0", 0),
    ([{"results": []}, {"results": [{"success": "false"}]}],
     "monitors=2 up=0 down=0 pending=1 unknown=1", 0),
    ([], "monitors=0 up=0 down=0 pending=0 unknown=0", 2),
    ({"endpoints": [{"results": [{"success": True}]}]},
     "structurally invalid", 2),
])
def test_gatus_api_reports_only_aggregate_latest_status(
    tmp_path: Path, entries, expected: str, exit_code: int
) -> None:
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    docker = fakebin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$1\" in\n"
        "  inspect) echo 'status=running health=none';;\n"
        "  logs) echo 'permission denied PRIVATE-TOKEN-DO-NOT-PRINT';;\n"
        "  *) exit 99;;\n"
        "esac\n", encoding="utf-8"
    )
    docker.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \" $* \" == *' --write-out '* ]]; then\n"
        "  printf '200'\n"
        "else\n"
        "  cat \"$GATUS_FAKE_JSON\"\n"
        "fi\n", encoding="utf-8"
    )
    curl.chmod(0o755)
    data = tmp_path / "status.json"
    data.write_text(json.dumps(entries) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"PATH": str(fakebin) + os.pathsep + env["PATH"],
                "GATUS_FAKE_JSON": str(data), "DIAG_COLOR": "never",
                "DIAG_ICONS": "never", "NO_COLOR": "1"})
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--check"], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=15, check=False
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == exit_code, output
    assert expected in output
    assert "PRIVATE-TOKEN" not in output
    assert "\"results\"" not in output


def test_gatus_status_diagnostic_is_read_only_and_valid_shell() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    assert "results[-1].success" in content
    assert "app.redeploy" not in content
    assert "gatus.db" in content  # metadata only; never altered
    assert "chmod " not in content
