"""Single-owner contract for platform diagnostic runbooks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_platform_runbook_ownership() -> None:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    pfsense = (ROOT / "docs/pfsense-diagnose-recover.md").read_text(
        encoding="utf-8"
    )
    platform = (ROOT / "docs/cloudflare-sentry-platform-diagnostics.md").read_text(
        encoding="utf-8"
    )

    assert "cloudflare-sentry-platform-diagnostics.md" in index
    assert "pfSense" in pfsense and "WebConfigurator" in pfsense
    assert "HTTP 502" in pfsense and "--unblock-sources" in pfsense
    assert "nabla-compose" in agents and "fastapi-sample" in agents
    assert "Sentry" in platform and "Cloudflare" in platform
    assert "synthetic event ID" in platform
    assert "fastapi-sample/blob/master/docs/" in platform
