from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAGGER = ROOT / "dagger.toml"
PACKAGE = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
MISE = ROOT / "mise.toml"
MISE_LOCK = ROOT / "mise.lock"
JUST = ROOT / "justfile"
ROADMAP = ROOT / "docs" / "roadmap.md"
SKILL = ROOT / ".agents" / "skills" / "local-first-quality" / "SKILL.md"
TASK_CONTEXT = ROOT / "scripts" / "agent-task-context.py"

DAGGER_STABLE = "0.21.10"
DAGGER_BETA = "v1.0.0-beta.15"
HYPERFINE = "2.0.0"
BIOME_VERSION = "2.4.12"
BIOME_BASE_IMAGE = (
    "node:25-alpine@sha256:"
    "f4769ca6eeb6ebbd15eb9c8233afed856e437b75f486f7fccaa81d7c8ad56007"
)
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
    assert "biscuitcutter.sh" in config["modules"]["shellcheck"]["settings"]["exclude"]
    assert (
        config["modules"]["biomejs"]["settings"]["baseImageAddress"]
        == BIOME_BASE_IMAGE
    )

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


def test_biome_dependency_matches_native_and_dagger_paths() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))

    assert package["devDependencies"]["@biomejs/biome"] == BIOME_VERSION
    assert lock["packages"][""]["devDependencies"]["@biomejs/biome"] == BIOME_VERSION

    biome = lock["packages"]["node_modules/@biomejs/biome"]
    assert biome["version"] == BIOME_VERSION
    assert biome["dev"] is True
    assert set(biome["optionalDependencies"].values()) == {BIOME_VERSION}

    platform_entries = [
        key
        for key in lock["packages"]
        if key.startswith("node_modules/@biomejs/cli-")
    ]
    assert len(platform_entries) == 8
    assert all(lock["packages"][key]["version"] == BIOME_VERSION for key in platform_entries)


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

    hyperfine_lock = lock["tools"]["hyperfine"][0]
    assert hyperfine_lock["version"] == HYPERFINE
    assert hyperfine_lock["backend"] == "aqua:sharkdp/hyperfine"
    assert hyperfine_lock["specifiers"] == [HYPERFINE]
    assert f'hyperfine = "{HYPERFINE}"' in mise


def test_just_keeps_dagger_poc_separate_from_publication_gate() -> None:
    just = JUST.read_text(encoding="utf-8")

    assert "\ndagger-sync:\n    mise run dagger-sync\n" in just
    assert "\ndagger-list:\n    mise run dagger-list\n" in just
    assert "\ndagger-poc:\n    mise run dagger-poc\n" in just
    assert "\ndagger-native-parity:\n    mise run dagger-native-parity\n" in just
    assert "\ndagger-bench:\n    mise run dagger-bench\n" in just
    assert "\npre-push:\n    mise run agent-pre-push\n" in just
    assert "dagger-poc:\n    mise run agent-pre-push" not in just


def test_dagger_requires_reviewed_lock_before_execution() -> None:
    mise = MISE.read_text(encoding="utf-8")

    assert mise.count('test -f dagger.lock || { echo "dagger.lock missing; run: just dagger-sync"; exit 2; }') >= 3
    assert "dagger workspace update did not create dagger.lock" in mise
    assert "git diff -- dagger.lock" in mise
    assert "pre-commit run shell-lint --all-files" in mise
    assert "pre-commit run biome-check --all-files" in mise
    assert "hyperfine --warmup 1 --runs 3" in mise
    assert "dagger cache" not in mise
    assert "docker system prune" not in mise


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
        "just dagger-native-parity",
        "just dagger-bench",
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


def test_dagger_changes_route_to_local_first_and_current_docs_skills() -> None:
    context = TASK_CONTEXT.read_text(encoding="utf-8")

    assert '"dagger.toml"' in context
    assert 'skills.add("local-first-quality")' in context
    assert 'skills.add("context7-docs")' in context
