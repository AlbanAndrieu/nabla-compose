"""famp-albandrieu: Access enforced at the edge AND verified by cloudflared (AUD tag)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workstation_route_requires_access_jwt_for_the_famp_app() -> None:
    tunnel = (ROOT / "terraform/cloudflare/tunnel-workstation.tofu").read_text(encoding="utf-8")
    route = tunnel.split('hostname = "famp-albandrieu.albandrieu.com"', 1)[1].split('service = "http://127.0.0.1:8082"', 1)[0]
    assert "required  = true" in route
    assert 'team_name = "albandrieu"' in route
    assert "aud_tag   = [cloudflare_zero_trust_access_application.famp_albandrieu.aud]" in route
    assert "depends_on = [cloudflare_zero_trust_access_application.famp_albandrieu]" in tunnel


def test_famp_access_app_is_identity_gated() -> None:
    access = (ROOT / "terraform/cloudflare/access.tofu").read_text(encoding="utf-8")
    block = access.split('"famp_albandrieu" {', 1)[1].split("\n}\n", 1)[0]
    assert "local.access_policy_nabla_id" in block
    assert "access_policy_everyone_bypass_id" not in block
