"""Offline tests for the private NetFlow v5 PCAP interface-index extractor."""
import importlib.util
import ipaddress
from pathlib import Path
import struct
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/inspect-netflow-v5-ifindex.py"
spec = importlib.util.spec_from_file_location("inspect_netflow_v5_ifindex", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def frame(pairs, version=5, vlan=False, dest="172.17.0.24"):
    netflow = struct.pack("!HH", version, len(pairs)) + bytes(20)
    netflow += b"".join(bytes(12) + struct.pack("!HH", a, b) + bytes(32) for a, b in pairs)
    udp = struct.pack("!HHHH", 38341, 2055, len(netflow) + 8, 0) + netflow
    ip = bytes([0x45, 0]) + struct.pack("!H", len(udp) + 20) + bytes(5)
    ip += bytes([17]) + bytes(2) + ipaddress.IPv4Address("172.17.0.1").packed
    ip += ipaddress.IPv4Address(dest).packed
    return bytes(12) + (bytes.fromhex("810000010800") if vlan else bytes.fromhex("0800")) + ip + udp


class IfIndexExtractionTests(unittest.TestCase):
    def test_extract_vlan_and_ifindex_zero(self):
        self.assertEqual(module.extract_ifindexes(frame([(11, 22), (11, 0)], vlan=True)),
                         [(11, 22), (11, 0)])

    def test_ignore_invalid_and_other_destinations(self):
        self.assertEqual(module.extract_ifindexes(frame([(1, 2)], version=9)), [])
        self.assertEqual(module.extract_ifindexes(frame([(1, 2)], dest="192.0.2.1")), [])
        self.assertEqual(module.extract_ifindexes(frame([(1, 2)])[:-4]), [])

    def test_classic_pcap_aggregation(self):
        packet = frame([(10, 20), (10, 30)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.pcap"
            path.write_bytes(bytes.fromhex("d4c3b2a1") +
                             struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 1) +
                             struct.pack("<IIII", 0, 0, len(packet), len(packet)) + packet)
            count, inputs, outputs = module.count_pcap(path)
            self.assertEqual(count, 1)
            self.assertEqual(inputs, {10: 2})
            self.assertEqual(outputs, {20: 1, 30: 1})


if __name__ == "__main__":
    unittest.main()
