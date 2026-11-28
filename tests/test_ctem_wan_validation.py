"""WAN scan rejects unsafe direct-IP targets before networking."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

file = Path(__file__).resolve().parents[1] / "scripts/security/validate-ctem-wan.py"
spec = spec_from_file_location("ctem_wan", file)
assert spec and spec.loader
mod = module_from_spec(spec)
spec.loader.exec_module(mod)


class CtemWanTests(unittest.TestCase):
    def test_only_globally_routable_unicast_v4(self):
        self.assertTrue(mod.valid_public_ipv4("82.66.4.247"))
        for candidate in ("", "172.17.0.24", "192.168.1.254", "10.0.0.1",
                          "127.0.0.1", "169.254.1.1", "224.0.0.1",
                          "255.255.255.255", "2001:4860:4860::8888",
                          "invalid", "0.0.0.0", "198.51.100.1"):
            with self.subTest(candidate=candidate):
                self.assertFalse(mod.valid_public_ipv4(candidate))


if __name__ == "__main__":
    unittest.main()
