"""Offline contracts for the bounded service diagnostics coordinator."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/truenas/diagnose-service-bundle.py"
)
SPEC = importlib.util.spec_from_file_location("diagnose_service_bundle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_plan_is_not_a_runtime_probe() -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), "--plan", "--section", "observability"],
        capture_output=True,
        check=False,
        text=True,
        timeout=6,
    )
    assert result.returncode == 0
    assert '"mode": "plan"' in result.stdout
    assert '"mutations": false' in result.stdout


def test_fixed_allowlist_no_shell_and_no_raw_output() -> None:
    seen: list[tuple[str, ...]] = []

    def fake_runner(args, **kwargs):
        seen.append(tuple(args))
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["check"] is False
        assert kwargs["timeout"] <= 45
        assert "shell" not in kwargs
        return SimpleNamespace(returncode=0)

    checks = MODULE.selected_checks("observability")
    results = MODULE.collect(checks, runner=fake_runner)
    assert MODULE.overall_exit(results) == 0
    assert len(seen) == 4
    assert set(x["state"] for x in results) == {"pass"}
    for command in seen:
        assert command[0] in {"python3", "bash"}
        assert command[1].startswith("scripts/")
        assert not any("sudo" in value or "--apply" in value for value in command)


def test_failure_isolation_and_no_false_green() -> None:
    count = 0

    def fake_runner(_args, **_kwargs):
        nonlocal count
        count += 1
        return SimpleNamespace(returncode=[1, 2, 0, 0][count - 1])

    results = MODULE.collect(
        MODULE.selected_checks("observability"), runner=fake_runner
    )
    assert count == 4
    assert [x["state"] for x in results] == [
        "unverified", "unverified", "pass", "pass",
    ]
    assert results[0]["reason"] == "nonzero_without_structured_evidence"
    assert results[0]["verdict"] == "UNVERIFIED"
    assert MODULE.overall_exit(results) == 2


def test_timeout_and_missing_tools_never_pass() -> None:
    def timeout(_args, **_kwargs):
        raise subprocess.TimeoutExpired("private", 5)

    results = MODULE.collect(
        (MODULE.selected_checks("observability")[0],), runner=timeout
    )
    assert results[0]["state"] == "timeout"
    assert results[0]["reason"] == "diagnostic_timed_out"
    assert results[0]["verdict"] == "UNVERIFIED"
    assert MODULE.overall_exit(results) == 2
    assert MODULE.overall_exit([{"state": "unverified"}]) == 2


def test_known_probe_failures_stay_fail_without_implying_service_down() -> None:
    assert MODULE.classify_exit_code(
        1, MODULE.Check("gatus", ("python3", "scripts/x.py"), 5,
                        exit_one_confirms_probe_failure=True),
    ) == ("failed", "confirmed_probe_failure")
    checks = (MODULE.Check(
        "gatus_monitors", ("python3", "scripts/truenas/diagnose-gatus-monitors.py"),
        10, exit_one_confirms_probe_failure=True,
    ),)
    rows = MODULE.collect(checks, runner=lambda *_a, **_kw: SimpleNamespace(returncode=1))
    assert rows[0]["state"] == "failed"
    assert rows[0]["verdict"] == "FAIL"
    assert rows[0]["evidence_scope"] == "probe_only"
    assert MODULE.overall_exit(rows) == 1


@pytest.mark.parametrize(
    ("code", "state", "reason"),
    [
        (0, "pass", "check_completed"),
        (1, "unverified", "nonzero_without_structured_evidence"),
        (2, "unverified", "diagnostic_incomplete"),
        (3, "unverified", "unexpected_exit_code"),
        (-9, "unverified", "unexpected_exit_code"),
        (None, "unverified", "invalid_exit_code"),
        (True, "unverified", "invalid_exit_code"),
    ],
)
def test_ambiguous_returncodes_never_claim_outage(code, state, reason) -> None:
    check = MODULE.Check("prometheus", ("python3", "scripts/x.py"), 5)
    assert MODULE.classify_exit_code(code, check) == (state, reason)


def test_missing_or_empty_evidence_is_never_full_success() -> None:
    assert MODULE.overall_exit([]) == 2
    assert MODULE.check_verdict("not_installed") == "NOT_RUN"
    assert MODULE.check_verdict("not_executed") == "UNVERIFIED"
    assert MODULE.check_verdict("timeout") == "UNVERIFIED"
    assert MODULE.check_verdict("failed") == "FAIL"
    assert MODULE.check_verdict("pass") == "PASS"


def test_summary_counts_all_five_verdicts_without_service_claims() -> None:
    rows = [
        {"verdict": "PASS"}, {"verdict": "DENIED"},
        {"verdict": "NOT_RUN"}, {"verdict": "UNVERIFIED"},
        {"verdict": "FAIL"}, {"verdict": "PASS"},
    ]
    assert MODULE.summarize_verdicts(rows) == {
        "PASS": 2, "FAIL": 1, "DENIED": 1, "UNVERIFIED": 1, "NOT_RUN": 1,
    }


def test_summary_missing_or_unknown_verdict_is_unverified() -> None:
    assert MODULE.summarize_verdicts([{}, {"verdict": "service_down"}]) == {
        "PASS": 0, "FAIL": 0, "DENIED": 0, "UNVERIFIED": 2, "NOT_RUN": 0,
    }


def test_summary_authoritative_execution_state_prevents_false_pass() -> None:
    rows = [
        {"state": "failed", "verdict": "PASS"},
        {"state": "timeout", "verdict": "PASS"},
        {"state": "not_installed", "verdict": "PASS"},
        {"state": "pass", "verdict": "FAIL"},
        {"state": "failed", "verdict": "FAIL"},
    ]
    summary = MODULE.summarize_verdicts(rows)
    assert summary["PASS"] == 1
    assert summary["FAIL"] == 2
    assert summary["UNVERIFIED"] == 1
    assert summary["NOT_RUN"] == 1


def test_summary_accepts_legacy_rows_and_non_dict_records() -> None:
    summary = MODULE.summarize_verdicts([
        {"verdict": "DENIED"}, {"verdict": "PASS"}, [],
        {"state": object(), "verdict": "PASS"},
    ])
    assert summary == {
        "PASS": 1, "FAIL": 0, "DENIED": 1, "UNVERIFIED": 2, "NOT_RUN": 0,
    }


def test_cli_exposes_probe_verdict_without_service_down_claim(monkeypatch, capsys):
    import json

    selected = MODULE.selected_checks("observability")
    rows = [
        {"name": selected[0].name, "state": "unverified",
         "verdict": "UNVERIFIED", "reason": "nonzero_without_structured_evidence",
         "evidence_scope": "probe_only", "exit_code": 1},
    ]
    monkeypatch.setattr(MODULE, "collect", lambda _checks: rows)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check", "--section", "observability"])
    assert MODULE.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "UNVERIFIED"
    assert payload["availability"] == "UNVERIFIED"
    assert payload["summary"]["UNVERIFIED"] == 1
    assert sum(payload["summary"].values()) == len(payload["checks"])
    assert payload["checks"][0]["evidence_scope"] == "probe_only"
    assert payload["mutations"] is False


@pytest.mark.parametrize("mode", ["--apply", "--restart", "--deploy"])
def test_mutating_args_rejected(mode: str) -> None:
    result = subprocess.run(
        ["python3", str(SCRIPT), mode],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_allowlist_has_no_dynamic_endpoints_or_logs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for unsafe in (
        "docker restart", "docker exec", "docker stop", "rm -rf",
        "sudo ", "os.system(", "shell=True", "print(finished.stdout)",
        "print(finished.stderr)", "http://", "https://",
    ):
        assert unsafe not in source
    assert "subprocess.DEVNULL" in source
    assert 'choices=SECTIONS' in source
