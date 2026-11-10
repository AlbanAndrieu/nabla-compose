"""Contract of terraform/cloudflaretokens (offline): least privilege, no committed client IP."""

from __future__ import annotations

from pathlib import Path
import re

UNIT = Path(__file__).resolve().parents[1] / "terraform" / "cloudflaretokens"


def source() -> str:
    return "".join(path.read_text(encoding="utf-8") for path in sorted(UNIT.glob("*.tofu")))


def test_opentofu_token_has_exactly_the_apply_permissions() -> None:
    text = source()
    assert 'opentofu_account_permissions = ["Access: Apps and Policies Write", "Cloudflare Tunnel Write"]' in text
    assert 'opentofu_zone_permissions    = ["DNS Write"]' in text
    assert '"com.cloudflare.api.account.zone.${var.zone_id}" = "*"' in text
    assert text.count('effect            = "allow"') == 2


def test_client_ips_come_from_the_operator_and_value_is_sensitive() -> None:
    text = source()
    assert "in = var.opentofu_token_client_ips" in text
    assert "default" not in text.split('variable "opentofu_token_client_ips"')[1].split("variable ")[0]
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}/\d+\b(?<!203\.0\.113\.7/32)", text)
    assert re.search(r'output "opentofu_token" \{[^}]*sensitive\s*=\s*true', text, re.S)
