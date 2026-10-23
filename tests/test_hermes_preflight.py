"""Offline tests for Hermes deployment preflight; synthetic secrets only."""

import importlib.util
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hermes/preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_preflight", SCRIPT)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


@pytest.fixture
def fixture_paths(tmp_path):
    env = tmp_path / "creds.env"
    state = tmp_path / "data"
    state.mkdir()
    os.chmod(state, 0o700)
    image = "nousresearch/hermes-agent@sha256:" + ("a" * 64)
    env.write_text(
        "HERMES_LITELLM_API_KEY=fake-token\n"
        "TELEGRAM_BOT_TOKEN=fake-bot-token\n"
        "TELEGRAM_ALLOWED_USERS=12345678\n",
        encoding="utf-8",
    )
    os.chmod(env, 0o600)
    return env, state, image


def test_preflight_never_discloses_values(fixture_paths):
    m = load_module()
    env, state, image = fixture_paths
    problems = m.validate(env, state, image, False)
    text = " ".join(problems)
    assert "fake-token" not in text and "fake-bot-token" not in text
    assert "Hermes UID 10000" in text  # tmp_path is not owned by container UID


def test_preflight_rejects_open_identity_and_unpinned_tag(fixture_paths):
    m = load_module()
    env, state, _image = fixture_paths
    with env.open("a", encoding="utf-8") as fd:
        fd.write("GATEWAY_ALLOW_ALL_USERS=true\n")
    problems = m.validate(env, state, "nousresearch/hermes-agent:stable", False)
    assert any("Image must be pinned" in x for x in problems)
    assert any("Unsafe allow-all" in x for x in problems)


def test_preflight_rejects_master_keys_and_missing_api_key(fixture_paths):
    m = load_module()
    env, state, image = fixture_paths
    with env.open("a", encoding="utf-8") as fd:
        fd.write("LITELLM_MASTER_KEY=never-leak\n")
    problems = m.validate(env, state, image, True)
    assert any("Privileged master" in x for x in problems)
    assert any("API_SERVER_KEY" in x for x in problems)
    assert "never-leak" not in " ".join(problems)


def test_preflight_blocks_symlinks(fixture_paths, tmp_path):
    m = load_module()
    env, state, image = fixture_paths
    link = tmp_path / "link.env"
    link.symlink_to(env)
    problems = m.validate(link, state, image, False)
    assert any("symlink" in x.lower() for x in problems)


def test_preflight_parser_refuses_duplicate_secret_keys(fixture_paths):
    m = load_module()
    env, _state, _image = fixture_paths
    with env.open("a", encoding="utf-8") as fd:
        fd.write("HERMES_LITELLM_API_KEY=again\n")
    with pytest.raises(ValueError, match="duplicated"):
        m.parse_names(env)


@pytest.mark.parametrize("line", [
    "TELEGRAM_ALLOWED_USERS=*",
    "GATEWAY_ALLOWED_USERS=12345678",
    "DISCORD_ALLOWED_CHANNELS=111222333",
])
def test_preflight_rejects_broad_authorization(fixture_paths, line):
    m = load_module()
    env, state, image = fixture_paths
    if line.startswith("TELEGRAM_ALLOWED_USERS="):
        original = env.read_text(encoding="utf-8")
        original = original.replace("TELEGRAM_ALLOWED_USERS=12345678", line)
        env.write_text(original, encoding="utf-8")
    else:
        with env.open("a", encoding="utf-8") as fd:
            fd.write(line + "\n")
    problems = m.validate(env, state, image, False)
    assert any("Allowlist" in text or "identity surface" in text for text in problems)


@pytest.mark.parametrize("upstream_key", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])
def test_preflight_forbids_upstream_provider_keys_in_hermes(fixture_paths, upstream_key):
    """Hermes is authorized only with HERMES_LITELLM_API_KEY, never vendor tokens."""
    m = load_module()
    env, state, image = fixture_paths
    with env.open("a", encoding="utf-8") as fd:
        fd.write(f"{upstream_key}=SECRET_VALUE_MUST_NOT_APPEAR\n")
    problems = m.validate(env, state, image, False)
    assert any("Privileged master" in problem for problem in problems)
    assert "SECRET_VALUE_MUST_NOT_APPEAR" not in " ".join(problems)
