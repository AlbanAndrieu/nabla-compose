"""Shared operator shell output contract (offline, no runtime access)."""

from pathlib import Path
import os
import pty
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "scripts/lib/common.sh"
HELPERS = 'source "$1"; ok done; info note; warn careful; section Step; fail broken'


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"LANG": "en_US.UTF-8"} | env_extra
    return subprocess.run(
        ["bash", "-c", HELPERS, "_", str(COMMON)],
        env=env, capture_output=True, text=True, check=False,
    )


def test_redirected_output_keeps_stable_plain_prefixes() -> None:
    result = _run({})
    assert result.returncode == 1
    assert result.stdout == "OK: done\nINFO: note\n\n==> Step\n"
    assert result.stderr == "WARN: careful\nERROR: broken\n"
    assert "\033[" not in result.stdout + result.stderr


def test_interactive_terminal_gets_icons_and_color_unless_no_color() -> None:
    def capture(env_extra: dict[str, str]) -> str:
        main, secondary = pty.openpty()
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "LC_ALL", "LC_CTYPE")}
        env |= {"LANG": "en_US.UTF-8", "TERM": "xterm-256color"} | env_extra
        # Read while the child runs: macOS drops pty output once the child exits.
        process = subprocess.Popen(
            ["bash", "-c", HELPERS, "_", str(COMMON)],
            env=env, stdin=secondary, stdout=secondary, stderr=secondary,
        )
        os.close(secondary)
        chunks = []
        while True:
            try:
                chunk = os.read(main, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        process.wait(timeout=10)
        os.close(main)
        return b"".join(chunks).decode("utf-8")

    colored = capture({})
    assert "\033[32m✅ OK:\033[0m done" in colored
    assert "\033[1;31m❌ ERROR:\033[0m broken" in colored
    ascii_only = capture({"NABLA_UI_ASCII": "1"})
    assert "\033[32mOK:\033[0m done" in ascii_only
    assert "✅" not in ascii_only
    plain = capture({"NO_COLOR": "1"})
    assert "\033[" not in plain
    assert "OK: done" in plain


def test_scripts_sourcing_common_do_not_redefine_fail() -> None:
    sources_common = re.compile(r'^source ".*lib/common\.sh"$', re.M)
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "scripts").rglob("*.sh"))
        if path != COMMON
        and sources_common.search(text := path.read_text(encoding="utf-8"))
        and re.search(r"^fail\(\)", text, re.M)
    ]
    assert offenders == []
