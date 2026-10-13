"""Read-only CLI/server compatibility audit regression contract."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-vaultwarden-cli.sh"


def test_diagnostic_is_syntactically_valid_and_nonmutating() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "2026.8.0" in source
    assert "2026.9.0" in source
    assert "KeyIdBackfillError" in source
    for action in ("bw login", "bw unlock", "bw sync", "bw logout", "npm install"):
        assert action not in source


def test_workstation_accepted_cli_with_locked_vault_is_not_failure(tmp_path: Path) -> None:
    fake = tmp_path / "bw"
    fake.write_text(
        "#!/bin/sh\n"
        "case \"$1 $2\" in\n"
        "  '--version ') echo 2026.8.0;;\n"
        "  'config server') echo https://vaultwarden.albandrieu.com;;\n"
        "  'status ') echo '{\"status\":\"locked\"}';;\n"
        "  *) exit 9;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["NABLA_BITWARDEN_CLI_COMPAT_VERSION"] = "2026.8.0"
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "runtime-accepted" in result.stdout
    assert "CLI is not unlocked" in result.stdout


def test_workstation_known_bad_cli_fails_without_running_migration(tmp_path: Path) -> None:
    fake = tmp_path / "bw"
    fake.write_text(
        "#!/bin/sh\n"
        "case \"$1 $2\" in\n"
        "  '--version ') echo 2026.9.0;;\n"
        "  'config server') echo https://vaultwarden.albandrieu.com;;\n"
        "  'status ') echo '{\"status\":\"locked\"}';;\n"
        "  *) exit 9;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "known incompatible" in result.stdout
