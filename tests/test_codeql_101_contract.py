"""Regression contract for CodeQL alert #101."""

from pathlib import Path


SCRIPT = Path("scripts/cloudflare/diagnose-cloudflare-api.py")
WORKFLOW = Path(".github/workflows/codeql.yml")


def test_access_redirect_detection_parses_hostname_instead_of_substring() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"cloudflareaccess.com" in location' not in source
    assert 'redirect_host == "cloudflareaccess.com"' in source
    assert 'redirect_host.endswith(".cloudflareaccess.com")' in source
    assert 'redirect_path.startswith("/cdn-cgi/access/")' in source


def test_codeql_analyzes_default_branch_pushes() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "push:" in workflow
    assert "branches: [master]" in workflow
