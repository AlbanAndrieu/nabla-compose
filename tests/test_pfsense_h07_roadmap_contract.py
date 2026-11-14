"""Keep open pfSense gaps visible in the active H07 roadmap."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pfsense_h07_open_gaps_and_historical_profile():
    doc = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    php = (ROOT / "docs/pfsense-php-fpm-hardening.md").read_text(encoding="utf-8")
    portfolio = (ROOT / "docs/roadmap-portfolio.md").read_text(encoding="utf-8")
    assert "### H07 — pfSense" in doc
    segment = doc.split("### H07 — pfSense", 1)[1].split("\n## ", 1)[0]
    for required in ("--check-posture", "DNSBL", "ASN reporting", "Snort",
                     "7 workers", "280 Mio", "4/30/1/2/500", "24/10"):
        assert required in segment
    assert "runtime" in segment or "relevé historique" in segment
    assert "H07" in portfolio and "Écarts pfSense ouverts" in portfolio
    assert "Backlog de réception H07" in php
