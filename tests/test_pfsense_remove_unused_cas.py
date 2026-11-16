"""Offline test of the pfSense helper removing unused expired or ACME issuer CAs."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/remove-unused-cas.php"

# Throwaway self-signed certificates (EC P-256, no key kept), valid 2020-2021 and 2020-2099.
EXPIRED_PEM = """-----BEGIN CERTIFICATE-----
MIIBbzCCARSgAwIBAgIUUxPo/x/u4ij0rM/5NyxW8DqZltIwCgYIKoZIzj0EAwIw
HTEbMBkGA1UEAwwSbmFibGEtdGVzdC1leHBpcmVkMB4XDTIwMDEwMTAwMDAwMFoX
DTIxMDEwMTAwMDAwMFowHTEbMBkGA1UEAwwSbmFibGEtdGVzdC1leHBpcmVkMFkw
EwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEEmjBq0g//rscTxk4oqUAO8hMQp2d981S
SOrUwxi+Li7pxVMyEljALu/jHnYo4rP+auhYmhYkK4HlSC3AUwNidaMyMDAwHQYD
VR0OBBYEFOqz+/HLbHlzuFYkNe7G+JFB1L0xMA8GA1UdEwEB/wQFMAMBAf8wCgYI
KoZIzj0EAwIDSQAwRgIhAKphBfww9K9UwKnYchuSKHgtiPqu5MzsMvwBHZ5n96FM
AiEA7++lxYoT86umV+IG/7pO7JaVlecAW/kyvJEBEjyEGtQ=
-----END CERTIFICATE-----
"""
VALID_PEM = """-----BEGIN CERTIFICATE-----
MIIBbDCCARKgAwIBAgIUSsYrp5BzGCQbcHVAWSEsnIMUnV8wCgYIKoZIzj0EAwIw
GzEZMBcGA1UEAwwQbmFibGEtdGVzdC12YWxpZDAgFw0yMDAxMDEwMDAwMDBaGA8y
MDk5MDEwMTAwMDAwMFowGzEZMBcGA1UEAwwQbmFibGEtdGVzdC12YWxpZDBZMBMG
ByqGSM49AgEGCCqGSM49AwEHA0IABE6xxv8zVygcGxe7T69NdszQId8IvzCmOkJq
PTIMldYU3WA7CeRGYXWkGbLlLCV5SrJbHLh0lXjaisivR7vBBlejMjAwMB0GA1Ud
DgQWBBSzhSkxma5Du0KGHm46jfIAnFqDaTAPBgNVHRMBAf8EBTADAQH/MAoGCCqG
SM49BAMCA0gAMEUCIDN/1ku+KOw1ldtilCk9/GeV1Y7+QyeIT9wz2An/yK7EAiEA
hX7r4UvlDarDn2Sm/Q+rDORhO8IDRiABITtTjYDSQrk=
-----END CERTIFICATE-----
"""

STUB = r"""<?php
$GLOBALS['cfg'] = json_decode(file_get_contents(getenv('STUB_CONFIG')), true);
function config_get_path($path, $default = null) {
    $c = $GLOBALS['cfg'];
    foreach (array_filter(explode('/', $path), 'strlen') as $k) {
        if (!is_array($c) || !array_key_exists($k, $c)) { return $default; }
        $c = $c[$k];
    }
    return $c;
}
function config_set_path($path, $value) { $GLOBALS['cfg'][$path] = $value; }
function write_config($desc) { file_put_contents(getenv('STUB_OUT'), json_encode($GLOBALS['cfg'])); }
"""


def crt(pem: str) -> str:
    return base64.b64encode(pem.encode()).decode()


def pfsense_config() -> dict:
    expired = crt(EXPIRED_PEM)
    return {
        "ca": [
            {"refid": "dead", "descr": "my_expressvpn_paris_CA", "crt": expired},
            {"refid": "used", "descr": "expired but a cert points at it", "crt": expired},
            {"refid": "ours", "descr": "expired internal CA", "crt": expired, "prv": "a2V5"},
            {"refid": "parent", "descr": "expired root of a live CA", "crt": expired},
            {"refid": "child", "descr": "valid intermediate", "crt": crt(VALID_PEM), "caref": "parent"},
            {"refid": "fresh", "descr": "valid and unused", "crt": crt(VALID_PEM)},
            {"refid": "r13", "descr": "Acmecert: O=Let's Encrypt, CN=R13, C=US", "crt": crt(VALID_PEM)},
            {"refid": "yr1", "descr": "Acmecert: O=Let's Encrypt, CN=YR1, C=US", "crt": crt(VALID_PEM)},
        ],
        "cert": [{"refid": "c1", "caref": "used"}, {"refid": "c2", "caref": "yr1"}],
    }


@unittest.skipUnless(shutil.which("php"), "php is required")
class RemoveExpiredUnusedCasTest(unittest.TestCase):
    def run_helper(self, mode: str, config: dict) -> tuple[subprocess.CompletedProcess, dict | None]:
        with tempfile.TemporaryDirectory(prefix="nabla-pfsense-ca-") as tmp:
            stubs = Path(tmp)
            (stubs / "config.inc").write_text(STUB, encoding="utf-8")
            (stubs / "config.json").write_text(json.dumps(config), encoding="utf-8")
            out = stubs / "written.json"
            result = subprocess.run(
                ["php", "-d", f"include_path={stubs}", "--", mode],
                input=SCRIPT.read_text(encoding="utf-8"),
                capture_output=True,
                text=True,
                env={**os.environ, "STUB_CONFIG": str(stubs / "config.json"), "STUB_OUT": str(out)},
                check=False,
            )
            written = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return result, written

    def test_check_reports_without_writing(self) -> None:
        result, written = self.run_helper("check", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CHANGE:"), 2)
        self.assertIn("CHANGE: ca dead my_expressvpn_paris_CA expired 2021-01-01", result.stdout)
        self.assertIn("CHANGE: ca r13 Acmecert: O=Let's Encrypt, CN=R13, C=US ACME issuer, unused", result.stdout)
        self.assertEqual(result.stdout.count("KEEP:"), 4)
        self.assertIsNone(written)

    def test_apply_removes_only_the_dead_ca_and_converges(self) -> None:
        result, written = self.run_helper("apply", pfsense_config())
        self.assertEqual(result.returncode, 0, result.stderr)
        assert written is not None
        self.assertEqual([ca["refid"] for ca in written["ca"]], ["used", "ours", "parent", "child", "fresh", "yr1"])
        again, rewritten = self.run_helper("apply", written)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("CHANGE:", again.stdout)
        self.assertIsNone(rewritten)


if __name__ == "__main__":
    unittest.main()
