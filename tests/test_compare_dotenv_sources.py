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


def test_normalize_keys_accepts_manifest_runtime_alias() -> None:
    normalized = compare.normalize_keys(
        {"CODE_PASSWORD": "same-secret"},
        {"CODE_PASSWORD": "PASSWORD"},
    )

    assert normalized == {"PASSWORD": "same-secret"}
    result = compare.compare_values(normalized, {"PASSWORD": "same-secret"})
    assert "same-secret" not in repr(result)


def test_normalize_keys_rejects_alias_value_conflict() -> None:
    try:
        compare.normalize_keys(
            {
                "CODE_PASSWORD": "legacy-secret",
                "PASSWORD": "different-secret",
            },
            {"CODE_PASSWORD": "PASSWORD"},
        )
    except compare.SecretsError as exc:
        assert "normalized key PASSWORD" in str(exc)
        assert "legacy-secret" not in str(exc)
        assert "different-secret" not in str(exc)
    else:
        raise AssertionError("alias conflict must fail closed")



def test_scrutiny_manifest_and_runtime_path_preserve_token_metadata() -> None:
    manifest = compare.load_manifest(compare.DEFAULT_MANIFEST)
    scrutiny = next(item for item in manifest["items"] if item["app"] == "scrutiny")
    names = [secret["env"] for secret in scrutiny["secrets"]]

    assert scrutiny["item"] == "nabla/prod/scrutiny"
    assert names == [
        "SCRUTINY_WEB_INFLUXDB_TOKEN",
        "SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION",
        "SCRUTINY_INFLUXDB_AUTH_ID",
    ]
    assert compare.app_key_aliases("scrutiny") == {}

    compose = (ROOT / "apps" / "scrutiny" / "compose.yml").read_text(encoding="utf-8")
    bootstrap = (
        ROOT / "scripts" / "truenas" / "bootstrap-scrutiny-influxdb.sh"
    ).read_text(encoding="utf-8")
    deploy = (ROOT / "scripts" / "truenas" / "deploy-scrutiny.sh").read_text(
        encoding="utf-8"
    )
    canonical = "/mnt/cpool/secrets/runtime/scrutiny/.env.secrets"
    legacy = "/mnt/cpool/scrutiny/.env.secrets"

    assert canonical in compose
    assert legacy not in compose
    assert canonical in bootstrap
    assert "SCRUTINY_LEGACY_SECRET_FILE" in bootstrap
    assert "SCRUTINY_TOKEN_ROTATE=1 only for an intentional rotation" in bootstrap
    assert bootstrap.index("legacy Scrutiny secret exists") < bootstrap.index(
        'create_bucket_if_missing "${BASE_BUCKET}"'
    )
    assert 'install -d -o root -g root -m 0700' in bootstrap
    assert canonical in deploy

def test_code_manifest_declares_legacy_to_runtime_alias() -> None:
    aliases = compare.app_key_aliases("code")

    assert aliases["CODE_PASSWORD"] == "PASSWORD"
