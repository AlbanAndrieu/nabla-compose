from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/talos/prepare-metallb-kubara.py"
MOD = runpy.run_path(str(SCRIPT))


class KubaraMetalLBTrialTests(unittest.TestCase):
    def test_reserved_ipv4_is_required_and_no_known_host_is_reused(self) -> None:
        valid = MOD["validated_vip"]("172.17.0.60")
        self.assertEqual(valid, ipaddress.IPv4Address("172.17.0.60"))
        for candidate in (
            "172.17.0.1",
            "172.17.0.24",
            "172.17.0.50",
            "172.17.0.51",
            "172.17.0.52",
            "172.17.0.57",
            "172.17.0.100",
            "172.17.0.200",
            "172.17.0.0",
            "172.17.0.255",
            "192.168.1.60",
            "127.0.0.1",
            "not-an-address",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    MOD["validated_vip"](candidate)

    def test_candidate_enables_metallb_without_changing_cilium_or_csi(self) -> None:
        before = (ROOT / "config/kubara/config.candidate.yaml").read_text()
        config = MOD["candidate"](ipaddress.IPv4Address("172.17.0.60"))
        service = config["clusters"][0]["services"]
        self.assertEqual(service["metallb"]["status"], "enabled")
        self.assertEqual(
            service["metallb"]["config"]["loadBalancerAddressPool"],
            ["172.17.0.60/32"],
        )
        self.assertEqual(service["traefik"], {"status": "enabled"})
        self.assertEqual(service["external-dns"], {"status": "disabled"})
        self.assertEqual(service["longhorn"], {"status": "disabled"})
        self.assertEqual(
            before, (ROOT / "config/kubara/config.candidate.yaml").read_text()
        )

    def test_staged_crd_limits_announcement_to_reviewed_pool(self) -> None:
        crds = MOD["expected_crds"](ipaddress.IPv4Address("172.17.0.60"))
        self.assertEqual(
            [x["kind"] for x in crds], ["IPAddressPool", "L2Advertisement"]
        )
        self.assertEqual(crds[0]["spec"]["addresses"], ["172.17.0.60/32"])
        self.assertFalse(crds[0]["spec"]["autoAssign"])
        self.assertEqual(
            crds[1]["spec"]["ipAddressPools"], ["nabla-talos-private"]
        )
        selectors = crds[1]["spec"]["nodeSelectors"]
        self.assertEqual(
            selectors[0]["matchExpressions"][0]["operator"], "DoesNotExist"
        )

    def test_render_is_private_offline_and_never_mutates_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review"
            path.mkdir()
            cmd = [
                "python3",
                str(SCRIPT),
                "--vip",
                "172.17.0.60",
                "--output-dir",
                str(path),
                "--ack-dhcp-reserved",
            ]
            run = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            report = json.loads(run.stdout)
            self.assertEqual(report["status"], "RENDERED_NOT_APPLIED")
            self.assertFalse(report["reserved_verified"])
            self.assertFalse(report["arp_verified"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            for name in report["files"]:
                self.assertEqual((path / name).stat().st_mode & 0o777, 0o600)
            config = yaml.safe_load((path / "config.yaml").read_text())
            self.assertEqual(
                config["clusters"][0]["services"]["metallb"]["status"],
                "enabled",
            )
            crds = list(
                yaml.safe_load_all(
                    (path / "metallb-intent.REVIEW-ONLY.yaml").read_text()
                )
            )
            self.assertEqual(len(crds), 2)
            self.assertIn("Do NOT kubectl apply", (path / "README.txt").read_text())

    def test_dry_run_needs_no_write_or_ack(self) -> None:
        run = subprocess.run(
            ["python3", str(SCRIPT), "--vip", "172.17.0.60"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(
            json.loads(run.stdout)["status"], "IP_ONLY_STATIC_CHECK_PASSED"
        )

    def test_fails_closed_without_reservation_or_with_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "review"
            dest.mkdir()
            cmd = [
                "python3",
                str(SCRIPT),
                "--vip",
                "172.17.0.60",
                "--output-dir",
                str(dest),
            ]
            denied = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(denied.returncode, 2)
            self.assertIn("DHCP_RESERVATION_ACK_REQUIRED", denied.stdout)
            (dest / "unexpected.txt").write_text("do not overwrite")
            denied = subprocess.run(
                [*cmd, "--ack-dhcp-reserved"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(denied.returncode, 2)
            self.assertIn("OUTPUT_DIR_NOT_EMPTY", denied.stdout)

    def test_no_kubernetes_mutation_api_or_direct_external_ip(self) -> None:
        src = SCRIPT.read_text()
        self.assertNotIn("import subprocess", src)
        self.assertNotIn("externalIPs:", src)
        self.assertNotIn("os.system", src)
        self.assertNotIn("autoAssign: true", src)


if __name__ == "__main__":
    unittest.main()
