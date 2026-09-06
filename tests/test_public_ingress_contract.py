from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PublicIngressContractTests(unittest.TestCase):
    def test_sample_has_separate_internal_and_public_traefik_routes(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("Host(`fastapi-sample.int.albandrieu.com`)", compose)
        self.assertIn("Host(`sample.albandrieu.com`)", compose)
        self.assertIn(
            "traefik.http.routers.fastapi-sample-public.tls.certresolver=letsencrypt",
            compose,
        )
        self.assertIn(
            "traefik.http.services.fastapi-sample.loadbalancer.server.port=8080",
            compose,
        )

    def test_sample_autoxpose_contract_is_dns_first_and_documented(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        for label in (
            "autoxpose.enable=auto",
            "autoxpose.subdomain=sample",
            "autoxpose.name=FastAPI Sample",
            "autoxpose.scheme=http",
            "autoxpose.port=${FASTAPI_SAMPLE_PORT:-8091}",
        ):
            self.assertIn(label, compose)
        self.assertNotIn("autoxpose.domain=", compose)

    def test_autoxpose_uses_shared_read_only_docker_proxy(self) -> None:
        compose = (ROOT / "apps" / "autoxpose" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("mostafawahied/autoxpose:0.4.2", compose)
        self.assertIn("DOCKER_HOST=tcp://docker-socket-proxy:2375", compose)
        self.assertIn("- intranet", compose)
        self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", compose)
        self.assertNotIn("172.17.0.24:2375", compose)

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
