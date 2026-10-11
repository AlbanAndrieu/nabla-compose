"""OpenClaw operator decorations never alter noninteractive evidence."""
from pathlib import Path
import importlib.util
import io
import os
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/openclaw-terminal-style.py"
spec = importlib.util.spec_from_file_location("openclaw_terminal_style", SCRIPT)
assert spec and spec.loader
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)


def test_plain_pipe_output_is_byte_identical() -> None:
    lines = ("failure_agent_runner=33\n", "status_ok=67\n", "private=unchanged\n")
    for line in lines:
        assert style.decorate(line, False) == line


def test_colorized_failures_and_safe_neutral_lines() -> None:
    assert "❌" in style.decorate("failure_agent_runner=33\n", True)
    assert "\x1b[31m" in style.decorate("embedding_auth_401=2\n", True)
    assert "✅" in style.decorate("openai_cli_key_parity=match\n", True)
    assert style.decorate("private-value=hidden\n", True) == "private-value=hidden\n"


def test_no_color_takes_precedence_over_force() -> None:
    with patch.dict(os.environ, {"NO_COLOR": "1", "OPENCLAW_COLOR": "always"}):
        assert not style.enabled()


def test_bash_entrypoints_parse() -> None:
    for name in ("openclaw-ops.sh", "diagnose-openclaw-errors.sh",
                 "backup-openclaw.sh", "diagnose-openclaw.sh",
                 "prepare-openclaw-systemd.sh"):
        subprocess.run(["bash", "-n", str(SCRIPT.parent / name)], check=True)
