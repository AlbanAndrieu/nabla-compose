from pathlib import Path


IMPORTER = Path("scripts/secrets/import_env_to_bitwarden.py")


def test_vaultwarden_importer_does_not_log_secret_environment_metadata() -> None:
    source = IMPORTER.read_text(encoding="utf-8")

    assert "source env:" not in source
    assert "join(sorted(missing))" not in source
    assert "missing_count" in source
    assert "names and values suppressed" in source
    assert "mapping_count = len(item[\"secrets\"])" in source
