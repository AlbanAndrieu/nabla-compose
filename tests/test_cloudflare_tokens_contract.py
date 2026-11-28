"""Contract of terraform/cloudflaretokens (offline): least privilege, no committed client IP."""

from __future__ import annotations

from pathlib import Path
import re

UNIT = Path(__file__).resolve().parents[1] / "terraform" / "cloudflaretokens"


def source() -> str:
    return "".join(path.read_text(encoding="utf-8") for path in sorted(UNIT.glob("*.tofu")))


def test_opentofu_token_has_exactly_the_apply_permissions() -> None:
    text = source()
    assert ('opentofu_account_permissions = ["Access: Apps and Policies Write", '
            '"Cloudflare Tunnel Write", "Workers Scripts Write"]') in text
    assert 'opentofu_zone_permissions    = ["DNS Write", "Workers Routes Write"]' in text
    # Zone permissions on the 20 zones of the account, listed by id (no wildcard).
    assert "concat([var.zone_id, var.albanandrieu_zone_id], values(var.mail_zone_ids))" in text
    assert "zone.*" not in text
    tfvars = (UNIT.parent / "cloudflare" / "mail-record-ids.auto.tfvars").read_text(encoding="utf-8")
    shared = tfvars.split("mail_zone_ids = {", 1)[1].split("}", 1)[0]
    default = text.split('variable "mail_zone_ids"', 1)[1].split("}\n}", 1)[0]
    assert sorted(re.findall(r'"([a-z0-9.-]+)"\s*=\s*"([0-9a-f]{32})"', default)) == sorted(
        re.findall(r'"([a-z0-9.-]+)"\s*=\s*"([0-9a-f]{32})"', shared))
    assert len(re.findall(r'"[0-9a-f]{32}"', shared)) == 18
    # Managed Transforms (managed-transforms.tofu): albandrieu.com only.
    assert 'opentofu_home_zone_permissions = ["Managed headers Write", "Bot Management Write"]' in text
    assert ('resources         = jsonencode({ "com.cloudflare.api.account.zone.${var.zone_id}" = "*" })'
            in text)
    assert text.count('effect            = "allow"') == 5


def test_crowdsec_bouncer_token_is_scoped_to_the_main_zone() -> None:
    text = source()
    block = text.split('resource "cloudflare_account_token" "crowdsec_bouncer"', 1)[1].split("\n}\n", 1)[0]
    assert '"com.cloudflare.api.account.zone.${var.zone_id}" = "*"' in block
    assert "in = var.opentofu_token_client_ips" in block
    assert "length(local.bouncer_missing_permissions) == 0" in block
    assert ('bouncer_zone_permissions    = ["DNS Read", "Workers Routes Write", "Zone Read"]') in text
    assert re.search(r'output "crowdsec_bouncer_token" \{[^}]*sensitive\s*=\s*true', text, re.S)


def test_client_ips_come_from_the_operator_and_value_is_sensitive() -> None:
    text = source()
    assert "in = var.opentofu_token_client_ips" in text
    assert "default" not in text.split('variable "opentofu_token_client_ips"')[1].split("variable ")[0]
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}/\d+\b(?<!203\.0\.113\.7/32)", text)
    assert re.search(r'output "opentofu_token" \{[^}]*sensitive\s*=\s*true', text, re.S)


def test_state_and_plans_are_encrypted_with_an_operator_passphrase() -> None:
    text = source()
    assert "passphrase = var.state_passphrase" in text
    for block in ("state", "plan"):
        assert re.search(rf"{block} \{{\s*method\s*=\s*method\.aes_gcm\.operator\s*enforced\s*=\s*true", text)
    assert "default" not in text.split('variable "state_passphrase"')[1].split("variable ")[0]
