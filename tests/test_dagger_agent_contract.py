from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAGGER = ROOT / "dagger.toml"
MISE = ROOT / "mise.toml"
MISE_LOCK = ROOT / "mise.lock"
JUST = ROOT / "justfile"
ROADMAP = ROOT / "docs" / "roadmap.md"
SKILL = ROOT / ".agents" / "skills" / "local-first-quality" / "SKILL.md"
TASK_CONTEXT = ROOT / "scripts" / "agent-task-context.py"

DAGGER_STABLE = "0.21.10"
DAGGER_BETA = "v1.0.0-beta.15"
SHELLCHECK_SOURCE = (
    "github.com/dagger/shellcheck@"
    "756497171e9185db48dc7961649f466b4003cfa9"
)
BIOME_SOURCE = (
    "github.com/dagger/biomejs@"
    "76dea6c9e0567da66fe2f2757d0d4204428b760f"
)


def test_dagger_workspace_is_bounded_and_secret_safe() -> None:
    config = tomllib.loads(DAGGER.read_text(encoding="utf-8"))

    assert config["defaults_from_dotenv"] is False
    assert config["check-generated"] is False
    assert config["modules"]["shellcheck"]["source"] == SHELLCHECK_SOURCE
    assert config["modules"]["biomejs"]["source"] == BIOME_SOURCE
    assert config["modules"]["shellcheck"]["settings"]["exclude"]

    sources = [module["source"] for module in config["modules"].values()]
    assert all(re.search(r"@[0-9a-f]{40}$", source) for source in sources)
    assert "pytest" not in config["modules"]
    assert "ruff" not in config["modules"]

    ignored = set(config["ignore"])
    for sensitive_or_heavy in (
        ".env",
        ".env.*",
        ".git/",
        ".ssh/",
        ".talos/",
        ".direnv/",
        ".venv/",
        "node_modules/",
        "reports/",
        "sentry/",
    ):
        assert sensitive_or_heavy in ignored


def test_dagger_cli_and_beta_workspace_are_explicitly_pinned() -> None:
    mise = MISE.read_text(encoding="utf-8")
    lock = tomllib.loads(MISE_LOCK.read_text(encoding="utf-8"))

    assert f'dagger = "{DAGGER_STABLE}"' in mise
    assert (
        f"dagger --x-release={DAGGER_BETA} workspace update --no-generate"
        in mise
    )
    assert f"dagger --x-release={DAGGER_BETA} check -l" in mise
    assert f"dagger --x-release={DAGGER_BETA} check --no-generate" in mise

    dagger_lock = lock["tools"]["dagger"][0]
    assert dagger_lock["version"] == DAGGER_STABLE
    assert dagger_lock["backend"] == "aqua:dagger/dagger"
    assert dagger_lock["specifiers"] == [DAGGER_STABLE]


def test_just_keeps_dagger_poc_separate_from_publication_gate() -> None:
    just = JUST.read_text(encoding="utf-8")

    assert "\ndagger-sync:\n    mise run dagger-sync\n" in just
    assert "\ndagger-list:\n    mise run dagger-list\n" in just
    assert "\ndagger-poc:\n    mise run dagger-poc\n" in just
    assert "\npre-push:\n    mise run agent-pre-push\n" in just
    assert "dagger-poc:\n    mise run agent-pre-push" not in just


def test_dagger_remains_experimental_until_parity_is_proven() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")

    for expected in (
        "ShellCheck + Biome",
        "Pytest",
        "root Python project marker",
        "just dagger-sync",
        "just dagger-list",
        "just dagger-poc",
        "agent-pre-push",
        "v1.0.0-beta.15",
    ):
        assert expected in roadmap

    assert "Experimental Dagger PoC" in skill
    assert "just dagger-sync" in skill
    assert "just dagger-list" in skill
    assert "just dagger-poc" in skill
    assert "does not replace the canonical publication gate" in skill
    assert "L1" in skill


def test_dagger_changes_route_to_local_first_skill() -> None:
    context = TASK_CONTEXT.read_text(encoding="utf-8")

    assert '"dagger.toml"' in context
    assert 'skills.add("local-first-quality")' in context
