"""Read-only, redacted Gatus triage contracts (offline)."""

from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-gatus.sh"


def test_script_syntax_and_forbidden_mutations() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    source = SCRIPT.read_text()
    assert "docker logs --tail 80" in source
    assert "docker inspect gatus" in source
    for forbidden in ("docker restart", "chmod ", "chown ", "docker run", "app.start", "app.update"):
        assert forbidden not in source


def test_diagnostic_does_not_leak_raw_logs(tmp_path: Path) -> None:
    docker = tmp_path / "docker"
    docker.write_text("""#!/usr/bin/env bash
if [[ "$1" == "inspect" ]]; then
  if [[ "$*" == *Mounts* ]]; then printf '/data true\\n'; else printf 'status=restarting exit=2\\n'; fi
elif [[ "$1" == "logs" ]]; then
  printf 'fatal sqlite permission denied TOKEN_SUPER_SECRET\\n'
else exit 1; fi
""")
    docker.chmod(0o755)
    env = os.environ | {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "permission=1" in result.stdout
    assert "database=1" in result.stdout
    assert "fatal=1" in result.stdout
    assert "TOKEN_SUPER_SECRET" not in result.stdout + result.stderr
