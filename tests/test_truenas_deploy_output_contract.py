"""Contracts for concise TrueNAS deployer output."""

from __future__ import annotations

from pathlib import Path
import subprocess


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

    assert 'smoke_name="nabla-dsomm-preflight-${BASHPID}"' in text
    assert 'smoke_name="nabla-dsomm-preflight-$"' not in text


def test_all_deployers_report_checkout_provenance() -> None:
    offenders: list[str] = []
    direct = 'truenas_repo_provenance "$(git rev-parse --show-toplevel)"'
    rooted = 'truenas_repo_provenance "${ROOT}"'
    root_from_script = 'ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"'
    for path in DEPLOYERS:
        text = path.read_text(encoding="utf-8")
        valid = direct in text or (rooted in text and root_from_script in text)
        if not valid:
            offenders.append(path.name)
    assert not offenders, f"deploy checkout provenance missing in: {offenders}"


def test_checkout_provenance_is_local_and_non_blocking() -> None:
    text = TRUENAS_LIB.read_text(encoding="utf-8")

    assert "truenas_repo_provenance()" in text
    assert "status --porcelain" in text
    assert "rev-list --left-right --count" in text
    assert "git fetch" not in text
    assert '0:*) relation="behind-${right}"' in text
    assert '*:0) relation="ahead-${left}"' in text
    assert '*) relation="diverged-${left}-${right}"' in text


def test_app_summary_renders_found_and_missing_apps_without_jq_errors() -> None:
    found_script = """
source "$1"
truenas_app_query_by_id() {
  printf '%s\\n' '[{"id":"crowdsec","state":"RUNNING","active_workloads":{"containers":1}}]'
}
truenas_app_summary crowdsec
"""
    found = subprocess.run(
        ["bash", "-c", found_script, "bash", str(TRUENAS_LIB)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode == 0, found.stderr
    assert (
        found.stdout.strip()
        == "OK: TrueNAS app crowdsec state=RUNNING containers=1"
    )

    missing_script = """
source "$1"
truenas_app_query_by_id() {
  printf '%s\\n' '[]'
}
truenas_app_summary "crowdsec-test"
"""
    missing = subprocess.run(
        ["bash", "-c", missing_script, "bash", str(TRUENAS_LIB)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 0, missing.stderr
    assert missing.stdout.strip() == "WARNING: TrueNAS app not found: crowdsec-test"


def test_compact_job_helper_preserves_failed_exit_status() -> None:
    script = """
source "$1"
sudo() { "$@"; }
midclt() {
  printf 'middleware failure\\n' >&2
  return 23
}
truenas_job_compact app.update dsomm '{}'
"""
    result = subprocess.run(
        ["bash", "-c", script, "bash", str(TRUENAS_LIB)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 23
    assert "TrueNAS job app.update failed (exit=23)" in result.stderr
    assert "middleware failure" in result.stderr
    assert "completed" not in result.stdout


def test_compact_job_helper_reports_success() -> None:
    script = """
source "$1"
sudo() { "$@"; }
midclt() {
  printf 'middleware success\\n'
  return 0
}
truenas_job_compact app.update dsomm '{}'
"""
    result = subprocess.run(
        ["bash", "-c", script, "bash", str(TRUENAS_LIB)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "OK: TrueNAS job app.update completed" in result.stdout
    assert "middleware success" not in result.stdout
