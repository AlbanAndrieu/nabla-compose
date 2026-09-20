from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "scripts" / "secrets"
sys.path.insert(0, str(SECRETS))
MODULE = SECRETS / "compare_dotenv_sources.py"
SPEC = importlib.util.spec_from_file_location("compare_dotenv_sources", MODULE)
assert SPEC and SPEC.loader
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def test_compare_values_reports_names_only() -> None:
    result = compare.compare_values(
        {
            "SHARED": "same-secret",
            "ROTATED": "old-secret",
            "LEFT_ONLY": "left-secret",
        },
        {
            "SHARED": "same-secret",
            "ROTATED": "new-secret",
            "RIGHT_ONLY": "right-secret",
        },
    )

    assert result == {
        "onlyLeft": ["LEFT_ONLY"],
        "onlyRight": ["RIGHT_ONLY"],
        "sameValue": ["SHARED"],
        "differentValue": ["ROTATED"],
    }
    assert "same-secret" not in repr(result)
    assert "old-secret" not in repr(result)
    assert "new-secret" not in repr(result)


def test_allowed_path_is_bounded_to_app_env_roots() -> None:
    assert compare.legacy.approved_app_env_path(
        "scrutiny",
        Path("/mnt/cpool/scrutiny/.env.secrets"),
    )
    assert compare.legacy.approved_app_env_path(
        "scrutiny",
        ROOT / "apps" / "scrutiny" / ".env.secrets",
    )
    assert compare.legacy.approved_app_env_path(
        "scrutiny",
        Path("/mnt/cpool/secrets/runtime/scrutiny/.env.secrets"),
    )
    assert not compare.legacy.approved_app_env_path(
        "scrutiny",
        Path("/mnt/cpool/other/.env.secrets"),
    )
    assert not compare.legacy.approved_app_env_path(
        "scrutiny",
        Path("/etc/shadow"),
    )
