"""Offline contract for a private DefectDojo HTTPS login probe."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/check-defectdojo-login-lan.sh"


@pytest.mark.parametrize(("probe", "expected_code", "expected_text"), [
    ("200|text/html; charset=utf-8|0", 0, "PASS:"),
    ("302|text/html|0", 2, "UNVERIFIED:"),
    ("403|text/html|0", 2, "UNVERIFIED:"),
    ("200|application/json|0", 1, "FAIL:"),
    ("200|text/html|60", 1, "FAIL:"),
    ("502|text/html|0", 1, "FAIL:"),
])
def test_pinned_login_probe(tmp_path, probe, expected_code, expected_text):
    fake = tmp_path / "curl"
    fake.write_text("#!/bin/bash\nprintf '%s' \"$MOCK_RESPONSE\"\n")
    fake.chmod(0o755)
    env = os.environ | {
        "PATH": str(tmp_path) + ":" + os.environ["PATH"],
        "MOCK_RESPONSE": probe,
    }
    result = subprocess.run(["bash", str(SCRIPT), "--check"],
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode == expected_code, result.stdout + result.stderr
    assert expected_text in result.stdout
    assert "tls_verify" in result.stdout


def test_source_has_no_insecure_tls_or_redirects():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--noproxy '*'" in source
    assert '--resolve "${HOST}:443:${EDGE}"' in source
    assert "--max-redirs 0" in source
    assert "--insecure" not in source
    assert "curl -k" not in source
