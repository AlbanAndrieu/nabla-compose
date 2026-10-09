"""Contracts for concise TrueNAS deployer output."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYERS = sorted((ROOT / "scripts" / "truenas").glob("deploy-*.sh"))
TRUENAS_LIB = ROOT / "scripts" / "lib" / "truenas.sh"


def test_all_deployers_use_compact_true_nas_jobs() -> None:
    offenders: list[str] = []
    for path in DEPLOYERS:
        text = path.read_text(encoding="utf-8")
        if "midclt call -j" in text:
            offenders.append(path.name)
    assert not offenders, f"raw TrueNAS job output remains in: {offenders}"


def test_compact_job_helper_is_bounded_and_verbose_opt_in() -> None:
    text = TRUENAS_LIB.read_text(encoding="utf-8")

    assert "truenas_job_compact()" in text
    assert "TRUENAS_DEPLOY_VERBOSE" in text
    assert "TRUENAS_JOB_LOG_TAIL" in text
    assert "last %s lines follow" in text
    assert "truenas_app_summary()" in text


def test_dsomm_smoke_name_is_valid_and_pid_scoped() -> None:
    text = (ROOT / "scripts" / "truenas" / "deploy-dsomm.sh").read_text(
        encoding="utf-8"
    )

    assert 'smoke_name="nabla-dsomm-preflight-$$"' in text
    assert 'smoke_name="nabla-dsomm-preflight-$"' not in text
