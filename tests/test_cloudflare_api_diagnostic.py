"""Contracts for the read-only Cloudflare API diagnostic."""

from pathlib import Path


SCRIPT = Path("scripts/cloudflare/diagnose-cloudflare-api.py")


def test_cloudflare_api_diagnostic_is_read_only_and_redacts_credentials() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'f"/accounts/{account_id}/tokens/verify"' in source
    assert '"/user/tokens/verify"' in source
    assert 'f"/accounts/{account_id}/cfd_tunnel?is_deleted=false&per_page=100"' in source
    assert 'f"/accounts/{account_id}/access/apps?per_page=100"' in source
    assert 'f"/accounts/{account_id}/access/policies?per_page=100"' in source
    assert 'method="GET"' in source
    assert "credentials are never printed" in source
    assert '"Authorization": f"Bearer {token}"' in source
    assert "socket.getaddrinfo(\"api.cloudflare.com\", 443" in source


def test_cloudflare_api_diagnostic_reads_runtime_credentials_from_environment() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()' in source
    assert 'os.getenv("CLOUDFLARE_API_TOKEN", "").strip()' in source
    assert "CLOUDFLARE_ACCOUNT_ID={'set' if account_set else 'MISSING'}" in source
    assert "CLOUDFLARE_API_TOKEN={'set' if token_set else 'MISSING'}" in source


def test_cloudflare_access_diagnostic_is_zone_bounded_and_redacted() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"--access-url"' in source
    assert "CLOUDFLARE_ACCESS_TEST_URL" in source
    assert "CF_ACCESS_CLIENT_ID" in source
    assert "CF_ACCESS_CLIENT_SECRET" in source
    assert '"CF-Access-Client-Id"' in source
    assert '"CF-Access-Client-Secret"' in source
    assert 'host == "albandrieu.com"' in source
    assert 'host.endswith(".albandrieu.com")' in source
    assert "Service Token was not sent" in source
    assert "Access Service Token probe" in source
    assert "policy assignment/precedence" in source
