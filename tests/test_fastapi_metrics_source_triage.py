"""Regression: source failures are classified safely, without revealing secrets."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'fastapi_metrics_triage', ROOT / 'scripts/truenas/reconcile-fastapi-metrics-credential.py'
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _source(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / 'sample.env'
    path.write_bytes(content)
    path.chmod(0o600)
    return path


KEY = b'0123456789abcdef' * 4


@pytest.mark.parametrize('data, expected', [
    (b'UNRELATED=do-not-print\n', 'source_key_missing'),
    (b'METRICS_SCRAPE_KEY=short\n', 'source_key_format_invalid'),
    (b'export METRICS_SCRAPE_KEY=' + KEY + b'\n', 'source_key_missing'),
    (b'METRICS_SCRAPE_KEY=' + KEY + b'\nMETRICS_SCRAPE_KEY=' + KEY + b'\n', 'source_key_duplicated'),
    (b'METRICS_SCRAPE_KEY=' + KEY + b'\nOTHER_SECRET=private\n', 'source_ready'),
    (b'METRICS_SCRAPE_KEY=' + KEY + b'\n', 'source_ready'),
    (b'METRICS_SCRAPE_KEY="' + KEY + b'"\n', 'source_ready'),
    (b'METRICS_SCRAPE_KEY=' + bytes([255]) + b'\n', 'source_encoding_invalid'),
])
def test_source_key_categories(tmp_path: Path, data: bytes, expected: str):
    p = _source(tmp_path, data)
    state, token = module.inspect_source(p, require_root=False)
    assert state == expected
    assert token == (KEY if state == 'source_ready' else None)


def test_missing_source_is_distinct(tmp_path: Path):
    state, token = module.inspect_source(tmp_path / 'absent.env', require_root=False)
    assert (state, token) == ('source_file_missing', None)


def test_symlink_and_hardlink_refused(tmp_path: Path):
    src = _source(tmp_path, b'METRICS_SCRAPE_KEY=' + KEY + b'\n')
    shortcut = tmp_path / 'link'
    shortcut.symlink_to(src)
    assert module.inspect_source(shortcut, require_root=False)[0] == 'source_symlink_refused'
    second = tmp_path / 'hardlink'
    os.link(src, second)
    assert module.inspect_source(src, require_root=False)[0] == 'source_hardlink_refused'


@pytest.mark.parametrize('mode', [0o666, 0o644, 0o660, 0o620, 0o400])
def test_restrict_source_permissions(tmp_path: Path, mode: int):
    src = _source(tmp_path, b'METRICS_SCRAPE_KEY=' + KEY + b'\n')
    src.chmod(mode)
    state = module.inspect_source(src, require_root=False)[0]
    assert state == ('source_ready' if mode == 0o400 else 'source_permissions_insecure')


def test_unprivileged_owner_mismatch_is_reported(tmp_path: Path):
    src = _source(tmp_path, b'METRICS_SCRAPE_KEY=' + KEY + b'\n')
    state = module.inspect_source(src, require_root=True)[0]
    assert state in ('source_owner_not_root', 'source_ready')
    if os.geteuid() != 0:
        assert state == 'source_owner_not_root'


def test_oversized_source_is_rejected(tmp_path: Path):
    src = _source(tmp_path, b'x' * (module.MAX_SOURCE_BYTES + 1))
    assert module.inspect_source(src, require_root=False)[0] == 'source_file_empty_or_oversized'


def test_check_returns_fixed_remediation_without_secret(tmp_path: Path, monkeypatch, capsys):
    src = _source(tmp_path, b'METRICS_SCRAPE_KEY=' + KEY + b'\n')
    src.chmod(0o644)
    monkeypatch.setattr(module, 'SOURCE', src)
    monkeypatch.setattr(module, 'inspect', lambda: 'source_permissions_insecure')
    assert module.main(['--check']) == 2
    body = capsys.readouterr().out
    answer = json.loads(body)
    assert answer['state'] == 'source_permissions_insecure'
    assert answer['next_check'] == 'review_source_secret_mode_without_dumping_file'
    assert '0123456789abcdef' not in body
    assert 'METRICS_SCRAPE_KEY' not in body
    assert str(src) not in body


def test_all_source_states_have_remediation():
    assert module.SOURCE_STATES.issubset(set(module.NEXT_CHECK))
