"""Offline contracts for unique pre-commit security/quality hook registration."""
from __future__ import annotations

import runpy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
module = runpy.run_path(str(ROOT / "scripts/quality/check-precommit-config.py"))
validate = module["validate"]
CONFIG = ROOT / ".pre-commit-config.yaml"


def test_real_precommit_manifest_is_valid_and_deduplicated():
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert validate(data) == []
    hooks = [hook["id"] for entry in data["repos"] for hook in entry["hooks"]]
    for required in ("actionlint", "zizmor", "betterleaks",
                     "compose-config", "security-ci-contract",
                     "truenas-csi-nfs-contract", "defectdojo-artifact-poller-contract",
                     "catalog-v2-native-identity-contract"):
        assert required in hooks
    assert len(hooks) == len(set(hooks))
    assert len(data["repos"]) <= 20  # Regression: four copies of security/quality checks


def test_duplicate_external_repo_is_detected():
    repo = {"repo": "https://example.invalid/hooks", "rev": "v1",
            "hooks": [{"id": "one"}]}
    assert validate({"repos": [repo, {"**": "unused", **repo}]}) == [
        "duplicate repository: https://example.invalid/hooks@v1",
        "duplicate hook id: one",
    ]


def test_duplicate_hook_across_local_repos_is_detected():
    data = {"repos": [{"repo": "local", "hooks": [{"id": "security"}]},
                      {"repo": "local", "hooks": [{"id": "security"}]}]}
    assert validate(data) == ["duplicate hook id: security"]


def test_missing_revision_is_fail_closed():
    data = {"repos": [{"repo": "https://example.invalid/hooks",
                        "hooks": [{"id": "check"}]}]}
    assert "missing revision pin" in validate(data)[0]


def test_invalid_manifest_shape_is_fail_closed():
    assert validate({}) == ["pre-commit config must contain a repos list"]
    assert validate({"repos": "not-a-list"}) == [
        "pre-commit config must contain a repos list"
    ]


def test_allows_multiple_distinct_local_groups():
    assert validate({"repos": [
        {"repo": "local", "hooks": [{"id": "shfmt"}]},
        {"repo": "local", "hooks": [{"id": "contract"}]},
    ]}) == []
