"""Security CI workflow regression contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codeql_is_a_pull_request_sast_gate() -> None:
    workflow = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "branches: [master]" in workflow
    assert "types: [opened, synchronize, reopened, ready_for_review]" in workflow
    assert "SAST / CodeQL (Python)" in workflow
    assert "github.event.pull_request.draft == false" in workflow
    assert "security-events: write" in workflow


def test_production_security_separates_pr_smoke_from_master_dast() -> None:
    workflow = (
        ROOT / ".github/workflows/production-security.yml"
    ).read_text(encoding="utf-8")

    assert "Production pre/post-deploy smoke" in workflow
    assert "https://fastapi-sample.fastapicloud.dev" in workflow
    assert "runtime-baseline.py integration" in workflow
    assert "runtime-baseline.py pentest" in workflow
    assert "DAST / OWASP ZAP (master)" in workflow
    assert "if: github.event_name != 'pull_request'" in workflow
    assert (
        "zaproxy/action-baseline@de8ad967d3548d44ef623df22cf95c3b0baf8b25"
        in workflow
    )
    assert "fail_action: true" in workflow
    assert "allow_issue_writing: false" in workflow


def test_pull_requests_require_a_fresh_successful_master_dast() -> None:
    workflow = (
        ROOT / ".github/workflows/production-security.yml"
    ).read_text(encoding="utf-8")

    assert "DAST master baseline gate" in workflow
    assert "actions: read" in workflow
    assert "branch=master&status=completed" in workflow
    assert "DAST_MAX_AGE_SECONDS: \"129600\"" in workflow
    assert 'conclusion}" != "success"' in workflow
    assert "production-security.yml is not on the PR base yet" in workflow
