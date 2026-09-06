from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PublicIngressContractTests(unittest.TestCase):
    def test_sample_internal_traefik_host_is_canonical_for_pihole_sync(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("APP_DOMAIN: sample.int.albandrieu.com", compose)
        self.assertIn("FASTAPI_RUNTIME_MODE: homelab", compose)
        self.assertIn("Host(`sample.int.albandrieu.com`)", compose)
        self.assertNotIn("fastapi-sample.int.albandrieu.com", compose)
        self.assertEqual(compose.count("traefik.http.routers.fastapi-sample.rule="), 1)
        self.assertIn(
            "traefik.http.services.fastapi-sample.loadbalancer.server.port=8080",
            compose,
        )

    def test_homelab_observer_keeps_appliance_probes_on_lan(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn('"truenas.albandrieu.com:172.17.0.24"', compose)
        self.assertIn('"home.albandrieu.com:172.17.0.1"', compose)
        self.assertIn("FASTAPI_RUNTIME_MODE: homelab", compose)

    def test_sample_public_path_is_not_owned_by_autoxpose_or_traefik(self) -> None:
        compose = (ROOT / "apps" / "sample" / "compose.yml").read_text(encoding="utf-8")

        self.assertNotIn("autoxpose.", compose)
        self.assertNotIn("Host(`sample.albandrieu.com`)", compose)
        self.assertNotIn("fastapi-sample-public", compose)

    def test_private_int_routes_do_not_enable_autoxpose(self) -> None:
        for compose_path in (ROOT / "apps").glob("*/compose.yml"):
            compose = compose_path.read_text(encoding="utf-8")
            if ".int.albandrieu.com" not in compose:
                continue
            self.assertNotIn(
                "autoxpose.enable=",
                compose,
                f"{compose_path.relative_to(ROOT)} mixes private .int routing with AutoXpose",
            )

    def test_dococd_uses_shared_internal_docker_proxy(self) -> None:
        compose = (ROOT / "docker-compose-truenas.yml").read_text(encoding="utf-8")

        self.assertIn("DOCKER_HOST: tcp://docker-socket-proxy:2375", compose)
        self.assertNotIn("DOCKER_HOST: tcp://172.17.0.24:2375", compose)
        dococd = compose.split("  doco-cd:", 1)[1].split("\nnetworks:", 1)[0]
        self.assertIn("- intranet", dococd)

    def test_autoxpose_uses_shared_read_only_docker_proxy(self) -> None:
        compose = (ROOT / "apps" / "autoxpose" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("mostafawahied/autoxpose:0.4.2", compose)
        self.assertIn("DOCKER_HOST=tcp://docker-socket-proxy:2375", compose)
        self.assertIn("- intranet", compose)
        self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", compose)
        self.assertNotIn("172.17.0.24:2375", compose)

    def test_autoxpose_has_local_http_healthcheck(self) -> None:
        compose = (ROOT / "apps" / "autoxpose" / "compose.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("healthcheck:", compose)
        self.assertIn("http://127.0.0.1:3000/api/settings/status", compose)
        self.assertIn("response.ok ? 0 : 1", compose)

    def test_garage_public_exception_is_s3_only(self) -> None:
        overrides = (
            ROOT / "catalog" / "homelab-exposure-overrides.json"
        ).read_text(encoding="utf-8")

        self.assertIn("Only the Garage S3 API", overrides)
        self.assertIn('"name": "Garage WebUI"', overrides)
        self.assertIn('"external": false', overrides)

    def test_pihole_sync_uses_shared_read_only_docker_proxy(self) -> None:
        compose = (ROOT / "apps" / "traefik" / "compose.yml").read_text(encoding="utf-8")

        self.assertIn("DOCKER_HOST: tcp://docker-socket-proxy:2375", compose)
        pihole = compose.split("  pihole-dns-sync:", 1)[1].split("  ddns-updater:", 1)[0]
        self.assertNotIn("/var/run/docker.sock", pihole)
        self.assertIn("- intranet", pihole)

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
        self.assertIn("Cloudflare token response: HTTP", script)
        self.assertIn("verify a Service Auth policy includes this token", script)
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

    def test_public_int_dns_audit_is_fail_closed(self) -> None:
        script = (ROOT / "scripts" / "security" / "audit-public-int-dns.sh").read_text(
            encoding="utf-8"
        )
        allowlist = (
            ROOT / "config" / "public-int-dns-exceptions.txt"
        ).read_text(encoding="utf-8")

        self.assertIn('endswith(".int.albandrieu.com")', script)
        self.assertIn("TEMPORARY-EXCEPTION", script)
        self.assertIn("UNEXPECTED", script)
        self.assertIn("exit 3", script)
        self.assertIn("s3.int.albandrieu.com", allowlist)
        self.assertIn("*.s3.int.albandrieu.com", allowlist)
        self.assertIn("vaultwarden.int.albandrieu.com", allowlist)
        self.assertNotIn("garage.int.albandrieu.com", allowlist)
        self.assertNotIn("garage-admin.int.albandrieu.com", allowlist)
        self.assertNotIn("ollama.int.albandrieu.com", allowlist)
        self.assertNotIn("hello.int.albandrieu.com", allowlist)

    def test_garage_host_ports_are_lan_bound(self) -> None:
        compose = (ROOT / "apps" / "garage" / "compose.yml").read_text(
            encoding="utf-8"
        )

        for port in ("3900", "3901", "3903", "3909"):
            self.assertIn(f'"172.17.0.24:{port}:{port}"', compose)
        self.assertIn('API_BASE_URL: "http://garage:3903"', compose)
        self.assertIn('S3_ENDPOINT_URL: "http://garage:3900"', compose)
        self.assertNotIn('"3903:3903"', compose)
        self.assertNotIn('"3909:3909"', compose)

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
