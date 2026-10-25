"""Offline checks for OpenRAG/OpenSearch secret equality (never emit values)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-openrag-opensearch-secret.sh"


def _test_with_synthetic_root(
    tmp_path: Path, credential: str, authority: str, *, apply: bool = False
) -> subprocess.CompletedProcess[str]:
    script_root = tmp_path / "scripts"
    (script_root / "truenas").mkdir(parents=True)
    (script_root / "lib").mkdir()
    source = SCRIPT.read_text(encoding="utf-8")
    # The root and ownership checks are bypassed ONLY in the copied fixture.
    # Production script always requires root and owner 0.
    source = source.replace(
        'require_root \'run as root on TrueNAS to read protected credentials\'',
        'true # synthetic non-root fixture',
    ).replace('[[ "$uid" == 0 &&', '[[ "$uid" =~ ^[0-9]+$ &&')
    (script_root / "truenas" / SCRIPT.name).write_text(source, encoding="utf-8")
    (script_root / "lib" / "common.sh").write_text(
        'fail() { printf "BLOCKED: %s\\n" "$1" >&2; exit 1; }\n'
        'require_commands() { for cmd in "$@"; do command -v "$cmd" >/dev/null || '
        'fail "missing command"; done; }\n',
        encoding="utf-8",
    )
    openrag = tmp_path / "openrag.env"
    search = tmp_path / "search.env"
    openrag.write_text("OPENSEARCH_PASSWORD=" + credential + "\n", encoding="utf-8")
    search.write_text("OPENSEARCH_PASSWORD=" + authority + "\n", encoding="utf-8")
    openrag.chmod(0o600)
    search.chmod(0o600)
    env = os.environ | {
        "OPENRAG_SECRET_FILE": str(openrag),
        "OPENSEARCH_ENV_FILE": str(search),
    }
    return subprocess.run(
        ["bash", str(script_root / "truenas" / SCRIPT.name),
         "--apply" if apply else "--check"],
        env=env, capture_output=True, text=True, check=False, timeout=8,
    )


@pytest.mark.parametrize("same,expected", [
    (True, 0),
    (False, 1),
])
def test_equality_is_read_only_and_no_secret_leak(
    tmp_path: Path, same: bool, expected: int
) -> None:
    secret = "never-disclose-the-password"
    candidate = secret if same else "different-never-disclose"
    result = _test_with_synthetic_root(tmp_path, secret, candidate)
    out = result.stdout + result.stderr
    assert result.returncode == expected, out
    assert secret not in out
    assert candidate not in out
    if same:
        assert "source_selection=operator_selected" in out
    else:
        assert "differs" in out


def test_unsafe_candidate_reports_class_but_not_secret(tmp_path: Path) -> None:
    marker = "never-echo-this-credential"
    # The check runs on a synthetic copy without a TrueNAS root requirement.
    # The candidate class is fixed: never print paths or dotenv values.
    result = _test_with_synthetic_root(tmp_path, marker, marker)
    assert result.returncode == 0
    source = SCRIPT.read_text(encoding="utf-8")
    for category in (
        "canonical_env", "canonical_secret", "legacy_env",
        "operator_selected",
    ):
        assert category in source
    assert "source=${candidate_class}" in source
    assert marker not in result.stdout + result.stderr


def test_legacy_apply_cannot_mutate_existing_file(tmp_path: Path) -> None:
    result = _test_with_synthetic_root(
        tmp_path, "do-not-replace", "other-secret", apply=True
    )
    assert result.returncode != 0
    assert "disabled" in result.stderr


def test_production_root_ownership_and_no_mutations_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'require_root \'run as root on TrueNAS to read protected credentials\'' in source
    assert '[[ "$uid" == 0' in source
    assert "/mnt/cpool/secrets/runtime/opensearch/.env" in source
    assert "OpenSearch canonical and legacy secret candidates disagree" in source
    assert "Legacy --apply disabled" in source
    assert "install -o" not in source
    assert "mktemp" not in source
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
