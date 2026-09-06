from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PublicIngressContractTests(unittest.TestCase):
    def test_sample_internal_traefik_hosts_are_canonical_and_compatible(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("APP_DOMAIN: sample.int.albandrieu.com", compose)
        self.assertIn("Host(`sample.int.albandrieu.com`)", compose)
        self.assertIn("Host(`fastapi-sample.int.albandrieu.com`)", compose)
        self.assertIn(
            "traefik.http.services.fastapi-sample.loadbalancer.server.port=8080",
            compose,
        )

    def test_sample_public_path_is_not_owned_by_autoxpose_or_traefik(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertNotIn("autoxpose.", compose)
        self.assertNotIn("Host(`sample.albandrieu.com`)", compose)
        self.assertNotIn("fastapi-sample-public", compose)

    def test_autoxpose_uses_shared_read_only_docker_proxy(self) -> None:
        compose = (ROOT / "apps" / "autoxpose" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("mostafawahied/autoxpose:0.4.2", compose)
        self.assertIn("DOCKER_HOST=tcp://docker-socket-proxy:2375", compose)
        self.assertIn("- intranet", compose)
        self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", compose)
        self.assertNotIn("172.17.0.24:2375", compose)

    def test_sample_acceptance_targets_truenas_and_cloudflare_access(self) -> None:
        script = (ROOT / "scripts" / "ingress" / "verify-sample-exposure.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('TRUENAS_HOST="${TRUENAS_HOST:-172.17.0.24}"', script)
        self.assertIn('INTERNAL_HOST="${INTERNAL_HOST:-sample.int.albandrieu.com}"', script)
        self.assertIn(
            'LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://${TRUENAS_HOST}:8091/health}"',
            script,
        )
        self.assertIn("CF-Access-Client-Id", script)
        self.assertIn("CF-Access-Client-Secret", script)
        self.assertIn("Cloudflare Access is enforcing authentication", script)
        self.assertNotIn("AUTOXPOSE_URL", script)
        self.assertNotIn("EXPECTED_PUBLIC_IP", script)
        self.assertNotIn("pfSense/HAProxy", script)

    def test_legacy_cloudflare_companion_cannot_own_sample_dns(self) -> None:
        compose = (ROOT / "apps" / "traefik" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn(
            "ghcr.io/tiredofit/docker-traefik-cloudflare-companion:7.4.0",
            compose,
        )
        self.assertIn(
            "DOMAIN1_EXCLUDED_SUB_DOMAINS=int,sample,static,test",
            compose,
        )
        self.assertNotIn("EXCLUDED_DOMAINS=", compose)

    def test_traefik_acme_contract_has_identity_dns01_and_persistent_store(self) -> None:
        compose = (ROOT / "apps" / "traefik" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("certificatesresolvers.letsencrypt.acme.email=", compose)
        self.assertIn(
            "certificatesresolvers.letsencrypt.acme.storage=/etc/traefik/certs/acme.json",
            compose,
        )
        self.assertIn(
            "certificatesresolvers.letsencrypt.acme.dnschallenge.provider=cloudflare",
            compose,
        )


if __name__ == "__main__":
    unittest.main()
