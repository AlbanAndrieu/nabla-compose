"""No-network, no-key-leak TrueNAS Hermes cloud preflight tests."""
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/check-litellm-hermes-credentials.py"
validate = runpy.run_path(str(SOURCE))["validate_file"]


def materialize(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".env.secrets"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_missing_key_names_are_reported_without_values(tmp_path):
    path = materialize(tmp_path, "ANTHROPIC_API_KEY=NOT-A-REAL-KEY\n")
    assert validate(path, require_root=False) == [
        "Missing or unprovisioned provider key: OPENAI_API_KEY"
    ]


def test_placeholder_key_blocks_activation(tmp_path):
    path = materialize(tmp_path, "ANTHROPIC_API_KEY=replace-me\nOPENAI_API_KEY=todo\n")
    errors = validate(path, require_root=False)
    assert len(errors) == 2
    assert "ANTHROPIC_API_KEY" in errors[0]
    assert "OPENAI_API_KEY" in errors[1]


def test_metadata_only_readiness_never_echoes_values(tmp_path):
    path = materialize(tmp_path,
        "ANTHROPIC_API_KEY=DO_NOT_LOG_TOKEN_ABC\n"
        "OPENAI_API_KEY=DO_NOT_LOG_TOKEN_DEF\n"
        "LITELLM_MASTER_KEY=DO_NOT_LOG_MASTER\n")
    errors = validate(path, require_root=False)
    assert errors == []
    assert all("DO_NOT_LOG" not in error for error in errors)


def test_permissive_file_permissions_fail_closed(tmp_path):
    path = materialize(tmp_path,
        "ANTHROPIC_API_KEY=opaque-one\nOPENAI_API_KEY=opaque-two\n")
    path.chmod(0o644)
    assert "mode 0600" in validate(path, require_root=False)[0]


def test_symlink_is_refused_without_following(tmp_path):
    path = materialize(tmp_path,
        "ANTHROPIC_API_KEY=opaque-one\nOPENAI_API_KEY=opaque-two\n")
    link = tmp_path / "linked.env"
    link.symlink_to(path)
    assert "symlink" in validate(link, require_root=False)[0]


def test_duplicate_and_malformed_entries_fail_closed(tmp_path):
    path = materialize(tmp_path,
        "ANTHROPIC_API_KEY=opaque-one\n"
        "ANTHROPIC_API_KEY=opaque-two\n"
        "OPENAI_API_KEY=opaque-three\n"
        "bad line\n")
    errors = validate(path, require_root=False)
    assert any("Duplicate LiteLLM" in e for e in errors)
    assert any("Malformed LiteLLM" in e for e in errors)


def test_not_ready_when_file_missing(tmp_path):
    assert "missing" in validate(tmp_path / "missing", require_root=False)[0]
