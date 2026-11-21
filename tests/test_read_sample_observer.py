"""Contract of scripts/truenas/read-sample-observer.sh: GET under /api only, key never in argv."""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/read-sample-observer.sh"


def test_rejects_paths_outside_api_before_reading_secrets(tmp_path: Path) -> None:
    for path in ("/admin", "http://evil/api", "/api/x;rm", "/api/$(id)"):
        result = subprocess.run(
            ["bash", str(SCRIPT), path], capture_output=True, text=True, check=False,
            env={"PATH": "/usr/bin:/bin", "SAMPLE_SECRETS_FILE": str(tmp_path / "absent")},
        )
        assert result.returncode == 2, path
        assert "usage:" in result.stderr


def test_key_reaches_curl_through_a_header_descriptor_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '--header @<(secrets_curl_headers X-Diagnostics-Key "${key}")' in text
    assert "echo" not in text and "set -x" not in text
