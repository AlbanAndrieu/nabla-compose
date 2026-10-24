#!/usr/bin/env python3
"""Extract aggregate NetFlow v5 input/output ifIndex numbers from private classic Ethernet PCAP."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import ipaddress
import struct
import sys

SOURCE = ipaddress.IPv4Address("172.17.0.1").packed
DEST = ipaddress.IPv4Address("172.17.0.24").packed
MAX_CAPTURE = 16 * 1024 * 1024


def extract_ifindexes(frame: bytes) -> list[tuple[int, int]]:
    if len(frame) < 14:
        return []
    offset = 14
    ethertype = int.from_bytes(frame[12:14], "big")
    for _ in range(2):
        if ethertype not in (0x8100, 0x88A8):
            break
        if len(frame) < offset + 4:
            return []
        ethertype = int.from_bytes(frame[offset + 2:offset + 4], "big")
        offset += 4
    if ethertype != 0x0800 or len(frame) < offset + 20:
        return []
    ip = frame[offset:]
    ihl = (ip[0] & 15) * 4
    if ip[0] >> 4 != 4 or ihl < 20 or len(ip) < ihl + 8 or ip[9] != 17:
        return []
    size = int.from_bytes(ip[2:4], "big")
    if size < ihl + 8 or size > len(ip) or int.from_bytes(ip[6:8], "big") & 0x3FFF:
        return []
    if ip[12:16] != SOURCE or ip[16:20] != DEST:
        return []
    udp = ip[ihl:size]
    length = int.from_bytes(udp[4:6], "big")
    if int.from_bytes(udp[2:4], "big") != 2055 or length < 8 or length > len(udp):
        return []
    payload = udp[8:length]
    if len(payload) < 24:
        return []
    version, count = struct.unpack_from("!HH", payload)
    if version != 5 or count == 0 or count > 30 or len(payload) != 24 + count * 48:
        return []
    return [struct.unpack_from("!HH", payload, 24 + i * 48 + 12) for i in range(count)]


def count_pcap(path: Path) -> tuple[int, Counter, Counter]:
    if path.stat().st_size > MAX_CAPTURE:
        raise ValueError("PCAP exceeds 16 MiB")
    with path.open("rb") as handle:
        header = handle.read(24)
        if len(header) != 24:
            raise ValueError("invalid header")
        endian = {
            b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
            b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">",
        }.get(header[:4])
        if endian is None or struct.unpack_from(endian + "I", header, 20)[0] != 1:
            raise ValueError("classic Ethernet PCAP required")
        packets = 0
        inputs, outputs = Counter(), Counter()
        while handle.tell() < path.stat().st_size:
            record = handle.read(16)
            if len(record) != 16:
                raise ValueError("truncated record")
            size = struct.unpack_from(endian + "I", record, 8)[0]
            if size > 65535:
                raise ValueError("invalid frame size")
            frame = handle.read(size)
            if len(frame) != size:
                raise ValueError("truncated frame")
            pairs = extract_ifindexes(frame)
            if pairs:
                packets += 1
                inputs.update(a for a, _ in pairs)
                outputs.update(b for _, b in pairs)
        return packets, inputs, outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", required=True, type=Path)
    args = parser.parse_args()
    try:
        packets, inputs, outputs = count_pcap(args.pcap)
    except (OSError, ValueError) as exc:
        print(f"ERROR: invalid private capture ({type(exc).__name__})", file=sys.stderr)
        return 2
    print(f"netflow_v5_datagrams={packets}")
    print(f"records={sum(inputs.values())}")
    for name, values in (("input_ifindex", inputs), ("output_ifindex", outputs)):
        for idx, n in sorted(values.items()):
            print(f"{name}={idx} records={n}")
    if 0 in inputs or 0 in outputs:
        print("WARNING: index 0 seen; do not assume a physical interface")
    return 0 if packets else 1


if __name__ == "__main__":
    raise SystemExit(main())
