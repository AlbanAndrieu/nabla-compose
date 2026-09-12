from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cloudflare" / "diagnose-cloudflare-api.py"
DOC = ROOT / "docs" / "cloudflare-zero-trust-observer.md"


def test_cloudflare_diagnostic_reads_dashboard_managed_tunnel_configuration() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "/cfd_tunnel/{args.tunnel_id}/configurations" in source
    assert "config.ingress" in source
    assert "--tunnel-id" in source
    assert "--expect-hostname" in source
    assert "Access reusable policies" in source
    assert "Access Service Tokens" in source


def test_access_probe_does_not_follow_login_redirects() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "class _NoRedirect(HTTPRedirectHandler)" in source
    assert "_ACCESS_OPENER.open" in source
    assert "anonymous_blocked is True and service_blocked is False" in source
    assert "Anonymous Access was not blocked" in source


def test_cloudflare_operator_doc_maps_dashboard_to_api() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "edit/public-hostname" in text
    assert "/one/access-controls/apps" in text
    assert "/one/access-controls/policies" in text
    assert "/one/access-controls/service-credentials/service-tokens" in text
    assert "result.config.ingress[]" in text
    assert "Service Auth" in text
