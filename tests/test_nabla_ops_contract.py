from __future__ import annotations

import json
import stat
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nabla_ops import (  # noqa: E402
    InitializationStage,
    ServiceIntent,
    advance_initialization_state,
    declared_apps,
    normalize_initialization_stage,
    normalize_service_intent,
    read_initialization_state,
    validate_initialization_transition,
)


def _catalog(status: str | None = None) -> dict:
    service = {
        "id": "example",
        "sourcePath": "apps/example/compose.yml",
        "composeService": "example",
        "runtime": {"provider": "truenas-app", "appId": "example"},
    }
    if status is not None:
        service["status"] = status
    return {"services": [service]}


def test_missing_status_falls_back_to_active() -> None:
    assert normalize_service_intent(None) is ServiceIntent.ACTIVE
    assert normalize_service_intent("") is ServiceIntent.ACTIVE


def test_planned_and_disabled_are_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text("services:\n  example:\n    image: example\n", encoding="utf-8")
        for status in ("planned", "disabled"):
            row = declared_apps(_catalog(status), root=root)[0]
            assert row["status"] == status
            assert row["initializationEligible"] is False


def test_active_service_is_initialization_eligible_by_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text("services:\n  example:\n    image: example\n", encoding="utf-8")
        row = declared_apps(_catalog(), root=root)[0]
        assert row["status"] == "active"
        assert row["initializationEligible"] is True


def test_manual_profile_is_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text(
            "services:\n  example:\n    image: example\n    profiles:\n      - manual\n",
            encoding="utf-8",
        )
        row = declared_apps(_catalog(), root=root)[0]
        assert row["manual"] is True
        assert row["initializationEligible"] is False


def test_manual_helper_does_not_disable_primary_runtime_service() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text(
            "services:\n"
            "  example:\n"
            "    image: example\n"
            "  maintenance:\n"
            "    image: example-maintenance\n"
            "    profiles:\n"
            "      - manual\n",
            encoding="utf-8",
        )
        row = declared_apps(_catalog(), root=root)[0]
        assert row["manual"] is False
        assert row["initializationEligible"] is True


def test_conflicting_runtime_ids_are_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    image: example-api\n"
            "  worker:\n"
            "    image: example-worker\n",
            encoding="utf-8",
        )
        catalog = {
            "services": [
                {
                    "id": "example-api",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "api",
                    "runtime": {
                        "provider": "truenas-app",
                        "appId": "example-a",
                    },
                },
                {
                    "id": "example-worker",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "worker",
                    "runtime": {
                        "provider": "truenas-app",
                        "appId": "example-b",
                    },
                },
            ]
        }

        row = declared_apps(catalog, root=root)[0]
        assert row["mappingError"] is not None
        assert row["runtimeId"] is None
        assert row["initializationEligible"] is False


def test_conflicting_service_statuses_are_not_initialization_eligible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        compose = root / "apps" / "example" / "compose.yml"
        compose.parent.mkdir(parents=True)
        compose.write_text(
            "services:\n"
            "  api:\n"
            "    image: example-api\n"
            "  worker:\n"
            "    image: example-worker\n",
            encoding="utf-8",
        )
        catalog = {
            "services": [
                {
                    "id": "example-api",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "api",
                    "status": "active",
                    "runtime": {"provider": "truenas-app", "appId": "example"},
                },
                {
                    "id": "example-worker",
                    "sourcePath": "apps/example/compose.yml",
                    "composeService": "worker",
                    "status": "planned",
                    "runtime": {"provider": "truenas-app", "appId": "example"},
                },
            ]
        }

        row = declared_apps(catalog, root=root)[0]
        assert row["statusError"] is not None
        assert row["status"] is None
        assert row["initializationEligible"] is False


def test_initialization_stage_order_is_stable() -> None:
    assert [stage.value for stage in InitializationStage] == [
        "DECLARED",
        "SECRETS_DECLARED",
        "SECRETS_MATERIALIZED",
        "DEPENDENCIES_READY",
        "DEPLOYED",
        "RUNTIME_ACCEPTED",
        "REBOOT_ACCEPTED",
    ]


def test_initialization_stage_normalization_is_strict() -> None:
    assert (
        normalize_initialization_stage("SECRETS_DECLARED")
        is InitializationStage.SECRETS_DECLARED
    )

    try:
        normalize_initialization_stage("secrets_declared")
    except ValueError as exc:
        assert "invalid initialization stage" in str(exc)
    else:
        raise AssertionError("lowercase initialization stage must be rejected")


def test_initialization_transitions_are_idempotent_or_single_step_only() -> None:
    stages = list(InitializationStage)

    for stage in stages:
        assert validate_initialization_transition(stage, stage) is stage

    for current, target in zip(stages, stages[1:], strict=True):
        assert validate_initialization_transition(current, target) is target

    for current, target in (
        (InitializationStage.DECLARED, InitializationStage.DEPENDENCIES_READY),
        (InitializationStage.RUNTIME_ACCEPTED, InitializationStage.DEPLOYED),
    ):
        try:
            validate_initialization_transition(current, target)
        except ValueError as exc:
            assert "advance exactly one stage" in str(exc)
        else:
            raise AssertionError(
                f"invalid initialization transition accepted: {current} -> {target}"
            )


def test_state_store_is_value_blind_atomic_and_monotonic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "service-state"

        declared = advance_initialization_state(
            "example",
            InitializationStage.DECLARED,
            root=root,
        )
        assert declared == {
            "version": 1,
            "serviceId": "example",
            "stage": "DECLARED",
            "transitionCount": 0,
        }

        state_path = root / "example.json"
        lock_path = root / "example.lock"
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
        assert set(json.loads(state_path.read_text(encoding="utf-8"))) == {
            "version",
            "serviceId",
            "stage",
            "transitionCount",
        }

        advanced = advance_initialization_state(
            "example",
            InitializationStage.SECRETS_DECLARED,
            root=root,
        )
        assert advanced["stage"] == "SECRETS_DECLARED"
        assert advanced["transitionCount"] == 1

        before = state_path.read_bytes()
        idempotent = advance_initialization_state(
            "example",
            InitializationStage.SECRETS_DECLARED,
            root=root,
        )
        assert idempotent == advanced
        assert state_path.read_bytes() == before

        try:
            advance_initialization_state(
                "example",
                InitializationStage.DEPLOYED,
                root=root,
            )
        except ValueError as exc:
            assert "advance exactly one stage" in str(exc)
        else:
            raise AssertionError("state store accepted a skipped transition")

        assert read_initialization_state("example", root=root) == advanced
        source = (
            ROOT / "scripts" / "nabla_ops" / "state.py"
        ).read_text(encoding="utf-8")
        assert "fcntl.flock" in source
        assert "os.replace" in source
        assert "os.fsync" in source


def test_state_store_rejects_mismatched_persisted_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "service-state"
        root.mkdir(mode=0o700)
        (root / "example.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "serviceId": "other",
                    "stage": "DECLARED",
                    "transitionCount": 0,
                }
            ),
            encoding="utf-8",
        )

        try:
            read_initialization_state("example", root=root)
        except ValueError as exc:
            assert "does not match expected" in str(exc)
        else:
            raise AssertionError("mismatched persisted service identity was accepted")


def test_state_cli_read_is_side_effect_free_for_missing_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "missing-state-root"
        result = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts" / "nabla-service.py"),
                "state",
                "--app",
                "example",
                "--state-root",
                str(root),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "persisted": False,
            "serviceId": "example",
            "stage": "DECLARED",
            "transitionCount": 0,
            "version": 1,
        }
        assert not root.exists()


def test_cli_is_read_only_and_emits_catalog_json() -> None:
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "nabla-service.py"),
            "catalog",
            "--json",
            "--include-non-active",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    by_app = {row["app"]: row for row in payload}
    assert by_app["opconnect"]["status"] == "disabled"
    assert by_app["opconnect"]["initializationEligible"] is False
    assert by_app["n8n"]["status"] == "planned"
    assert by_app["n8n"]["initializationEligible"] is False
