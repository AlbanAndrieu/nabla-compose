"""Offline recovery contracts: no TrueNAS/network calls or leaked secrets."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mod = runpy.run_path(str(ROOT / "scripts/truenas/diagnose-ai-secret-recovery.py"))
check_secret = mod["check_secret"]


def create(tmp_path: Path, text: str) -> Path:
    f = tmp_path / ".env.secrets"
    f.write_text(text, encoding="utf-8")
    f.chmod(0o600)
    return f


def test_missing_litellm_secret_is_blocker(tmp_path):
    report = check_secret(tmp_path / "missing", ("LITELLM_MASTER_KEY",),
                          require_root=False)
    assert report["ready"] is False
    assert any("missing" in issue for issue in report["issues"])
    assert "LITELLM_MASTER_KEY" not in str(report.get("path", ""))


def test_litellm_keys_redacted_and_anthropic_optional(tmp_path):
    f = create(tmp_path, "LITELLM_MASTER_KEY=supersecret\n"
               "LITELLM_SALT_KEY=opaque\n")
    report = check_secret(f, ("LITELLM_MASTER_KEY", "LITELLM_SALT_KEY"),
                          require_root=False)
    assert report["ready"] is True
    assert "supersecret" not in json.dumps(report)
    assert "Anthropic not provisioned" in " ".join(report["notes"])


def test_empty_required_token_not_accepted(tmp_path):
    f = create(tmp_path, "LITELLM_MASTER_KEY=\n")
    report = check_secret(f, ("LITELLM_MASTER_KEY",), require_root=False)
    assert report["ready"] is False
    assert any("empty value" in issue for issue in report["issues"])


def test_openrag_encryption_key_requires_32_base64_decoded_bytes(tmp_path):
    import base64
    import secrets

    raw = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    original = "OPENSEARCH_PASSWORD=opaque\nLANGFLOW_KEY=opaque\n"
    original += "LITELLM_IDE_API_KEY=opaque\n"
    file = create(tmp_path, original + "OPENRAG_ENCRYPTION_KEY=" + raw + "\n")
    required = mod["REQUIRED_KEYS"]["openrag"]
    report = check_secret(file, required, require_root=False)
    assert report["ready"] is True, report["issues"]
    assert raw not in json.dumps(report)

    file.write_text(original + "OPENRAG_ENCRYPTION_KEY=" + "a" * 64 + "\n")
    report = check_secret(file, required, require_root=False)
    assert report["ready"] is False
    assert any("32 bytes" in issue for issue in report["issues"])
    assert "a" * 64 not in json.dumps(report)


def test_unbalanced_dotenv_quote_is_not_accepted(tmp_path):
    file = create(tmp_path, 'LITELLM_N8N_API_KEY=not-a-secret"\n')
    result = check_secret(file, (), require_root=False)
    assert result["ready"] is False
    assert "malformed dotenv quoting: LITELLM_N8N_API_KEY" in result["issues"]
    assert "not-a-secret" not in json.dumps(result)


def test_litellm_requires_both_langfuse_project_api_keys(tmp_path):
    keys = "LITELLM_MASTER_KEY=opaque\nLITELLM_SALT_KEY=opaque\n"
    keys += "LITELLM_IDE_API_KEY=opaque\nREDIS_URL=opaque\n"
    file = create(tmp_path, keys + "LANGFUSE_SECRET_KEY=sk-lf-synthetic\n")
    required = mod["REQUIRED_KEYS"]["litellm"]
    result = check_secret(file, required, require_root=False)
    assert not result["ready"]
    assert result["missingKeys"] == ["LANGFUSE_PUBLIC_KEY"]
    file.write_text(keys + "LANGFUSE_SECRET_KEY=sk-lf-synthetic\n"
                    "LANGFUSE_PUBLIC_KEY=pk-lf-synthetic\n")
    assert check_secret(file, required, require_root=False)["ready"]


def test_scrutiny_scope_v2_required(tmp_path):
    f = create(tmp_path, "SCRUTINY_WEB_INFLUXDB_TOKEN=opaque\n"
               "SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION=1\n")
    report = check_secret(f, ("SCRUTINY_WEB_INFLUXDB_TOKEN",),
                          require_root=False)
    assert report["ready"] is False
    assert any("scoped token v2" in issue for issue in report["issues"])
    f.write_text("SCRUTINY_WEB_INFLUXDB_TOKEN=opaque\n"
                 "SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION=2\n")
    assert check_secret(f, ("SCRUTINY_WEB_INFLUXDB_TOKEN",),
                        require_root=False)["ready"] is True


def test_dangerous_permissions_and_symlink_rejected(tmp_path):
    f = create(tmp_path, "LITELLM_MASTER_KEY=opaque\n")
    f.chmod(0o644)
    assert not check_secret(f, ("LITELLM_MASTER_KEY",),
                            require_root=False)["ready"]
    f.chmod(0o600)
    symlink = tmp_path / "symlink.env"
    symlink.symlink_to(f)
    assert not check_secret(symlink, ("LITELLM_MASTER_KEY",),
                            require_root=False)["ready"]


def test_deployed_scrutiny_legacy_path_is_metadata_only(monkeypatch):
    query = mod["query_app"]
    secret_string = "PASSWORD=NEVER_RETURN_ME"
    payload = [{
        "id": "scrutiny", "state": "STOPPED",
        "custom_compose_config_string": (
            "env_file:\n  - /mnt/cpool/scrutiny/.env.secrets\n" + secret_string
        ),
    }]
    monkeypatch.setitem(query.__globals__, "call",
                        lambda *args, **kwargs: json.dumps(payload))
    info = query("scrutiny")
    assert info["legacyScrutinyEnvFile"] is True
    assert info["state"] == "STOPPED"
    assert "NEVER_RETURN_ME" not in json.dumps(info)


def test_no_service_secret_in_container_health(monkeypatch):
    check = mod["inspect_container"]
    monkeypatch.setitem(check.__globals__, "call", lambda *args, **kwargs:
                        json.dumps({"Status": "exited", "ExitCode": 1,
                                    "OOMKilled": False,
                                    "Health": {"Status": "unhealthy",
                                               "Log": [{"Output": "PASSWORD=PRIVATE"}]}}))
    row = check("openrag-backend")
    assert row["health"] == "unhealthy"
    assert "PRIVATE" not in json.dumps(row)


def test_failed_middleware_query_is_not_reported_healthy(monkeypatch):
    query = mod["query_app"]
    monkeypatch.setitem(query.__globals__, "call",
                        lambda *args, **kwargs: None)
    assert query("litellm")["state"] == "UNVERIFIED"


def test_strict_mode_blocks_runtime_failure_without_leaking(monkeypatch, capsys):
    main = mod["main"]
    monkeypatch.setattr(main.__globals__["os"], "geteuid", lambda: 0)
    monkeypatch.setitem(main.__globals__, "assess",
                        lambda scope="all": {"readOnly": True, "blockers": [
                            "litellm: restore canonical Vaultwarden runtime secrets"
                        ]})
    assert main(["--check", "--strict"]) == 1
    text = capsys.readouterr().out
    assert '"blockers"' in text
    assert "ANTHROPIC_API_KEY" not in text
    assert main(["--check"]) == 0


def test_malformed_middleware_response_fails_closed(monkeypatch):
    query = mod["query_app"]
    monkeypatch.setitem(query.__globals__, "call",
                        lambda *args, **kwargs: '{"unexpected":"shape"}')
    assert query("scrutiny")["state"] == "UNVERIFIED"
