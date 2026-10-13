"""Static non-deploying Hermes Secure by Design policy contract."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config/hermes/secure-profile.example.yaml"
ADR = ROOT / "docs/security/hermes-secure-by-design.md"


def test_secure_profile_explicitly_denies_unsafe_modes():
    policy = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert policy["approvals"]["mode"] == "manual"
    for unattended in ("cron_mode", "single_query_mode", "unattended_mode"):
        assert policy["approvals"][unattended] == "deny"
    assert policy["unauthorized_dm_behavior"] == "ignore"
    assert policy["security"]["redact_secrets"] is True


def test_secure_profile_never_rescues_search_to_external_free_providers():
    web = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))["web"]
    assert web["backend"] == "searxng"
    assert web["search_backend"] == "searxng"
    assert web["keyless_fallback"] is False
    assert web["keyless_rescue"] is False
    assert web.get("extract_backend") in (None, "searxng")


def test_secure_profile_does_not_run_shell_on_host_or_forward_credentials():
    cfg = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert cfg["terminal"]["backend"] == "ssh"  # isolated non-root worker only
    assert cfg["terminal"]["home_mode"] == "profile"
    assert cfg["terminal"]["env_passthrough"] == []


def test_skill_and_memory_writes_need_approval():
    cfg = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert cfg["skills"]["guard_agent_created"] is True
    assert cfg["skills"]["write_approval"] is True
    assert cfg["memory"]["write_approval"] is True


def test_security_plan_prohibits_root_docker_socket_and_raw_pii_egress():
    doc = ADR.read_text(encoding="utf-8")
    for important in (
        "socket Docker",
        "master",
        "store_prompts_in_spend_logs: true",
        "turn_off_message_logging: false",
        "keyless_rescue",
        "Bitwarden Secrets Manager",
        "web_extract",
        "PromptInjection",
        "Telegram/Discord",
    ):
        assert important in doc
