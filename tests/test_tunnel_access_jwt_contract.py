"""Every tunnel route verifies the Access JWT in cloudflared, or is a documented bypass."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "terraform/cloudflare"
# Access bypass issues no JWT: requiring one would break these routes.
BYPASS = {
    "keycloak.albandrieu.com",  # OIDC realm bypass
    "login.albandrieu.com",  # public honeypot
    "joplin.albandrieu.com",  # sync clients, Everyone bypass
    "n8n.albandrieu.com",  # Slack OAuth callback bypass path
    "vaultwarden.albandrieu.com",  # Bitwarden clients, Everyone bypass
    "fastapi-sample.albandrieu.com",  # GitHub webhook bypass path
}


def _routes(text: str) -> list[tuple[str, str]]:
    blocks = re.split(r"\n    \{\n", text)
    out = []
    for block in blocks:
        host = re.search(r'hostname\s*=\s*"([^"]+)"', block)
        if host:
            out.append((host.group(1), block))
    return out


def test_every_route_requires_the_access_jwt_or_is_a_listed_bypass() -> None:
    tunnel = (CF / "tunnel.tofu").read_text(encoding="utf-8")
    jwt = (CF / "access-jwt.tofu").read_text(encoding="utf-8")
    for host, block in _routes(tunnel):
        if 'service        = "http_status:404"' in block or host in BYPASS:
            assert f'local.access_jwt["{host}"]' not in block, host
            continue
        assert f'local.access_jwt["{host}"]' in block, f"{host}: add its AUD to access-jwt.tofu or document a bypass"
        assert f'"{host}"' in jwt, host


def test_access_jwt_is_required_with_the_team_and_route_aud() -> None:
    jwt = (CF / "access-jwt.tofu").read_text(encoding="utf-8")
    assert 'access_team_name = "albandrieu"' in jwt
    assert "required  = true" in jwt
    assert "aud_tag   = [aud]" in jwt
    assert "uuid" not in jwt and not re.search(r'"[0-9a-f]{64}"', jwt), "reference .aud, never a pasted tag"


def test_route_applications_are_imported_with_their_private_destinations() -> None:
    apps = (CF / "access-routes.tofu").read_text(encoding="utf-8")
    ids = (CF / "access-application-ids.auto.tfvars").read_text(encoding="utf-8")
    imports = (CF / "imports.tofu").read_text(encoding="utf-8")
    assert "for_each = var.route_access_application_ids" in imports
    for name in re.findall(r'^    "([a-z0-9-]+)" = \{', apps, re.M):
        assert f'"{name}"' in ids, name
    assert 'type = "private"' in apps
    assert "prevent_destroy = true" in apps
