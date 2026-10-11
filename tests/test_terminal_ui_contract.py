"""Status UI remains safe for logs/pipes and usable on interactive terminals."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts/lib/terminal-ui.sh"


def test_library_syntax_and_no_side_effects() -> None:
    assert subprocess.run(["bash", "-n", str(LIB)], check=False).returncode == 0
    text = LIB.read_text()
    assert "docker " not in text
    assert "midclt " not in text


def test_non_tty_is_plain_text() -> None:
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; nabla_ui_init; nabla_ui_status ok ready', "test", str(LIB)],
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "OK ready\n"
    assert "\x1b[" not in result.stdout


def test_invalid_status_fails() -> None:
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; nabla_ui_init; nabla_ui_status unknown ready', "test", str(LIB)],
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert result.returncode == 2
