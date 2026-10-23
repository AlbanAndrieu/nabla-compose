#!/usr/bin/env python3
"""Synthetic attestation tests using ephemeral in-memory keys; no reader access."""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier

source = Path(__file__).with_name("verify-age-yubikey-piv82-attestation.py")
spec = importlib.util.spec_from_file_location("piv82_attestation", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW = dt.datetime.now(dt.timezone.utc)


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def cert(subject, issuer, public, signer, *, ca=False, policy=None, serial=None,
         valid=True):
    start = NOW - dt.timedelta(days=1)
    end = NOW + dt.timedelta(days=1) if valid else NOW - dt.timedelta(hours=1)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
               .public_key(public).serial_number(x509.random_serial_number())
               .not_valid_before(start).not_valid_after(end)
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if policy is not None:
        builder = builder.add_extension(x509.UnrecognizedExtension(
            ObjectIdentifier(module.POLICY_OID), policy), critical=False)
    if serial is not None:
        builder = builder.add_extension(x509.UnrecognizedExtension(
            ObjectIdentifier(module.SERIAL_OID), int(serial).to_bytes(4, "big")), critical=False)
    return builder.sign(signer, hashes.SHA256())


def main():
    root_key = ec.generate_private_key(ec.SECP256R1())
    ca_key = ec.generate_private_key(ec.SECP256R1())
    f9_key = ec.generate_private_key(ec.SECP256R1())
    slot_key = ec.generate_private_key(ec.SECP256R1())
    root_name, ca_name, f9_name = name("synthetic trusted root"), name("synthetic CA"), name("synthetic F9")
    root = cert(root_name, root_name, root_key.public_key(), root_key, ca=True)
    ca = cert(ca_name, root_name, ca_key.public_key(), root_key, ca=True)
    f9 = cert(f9_name, ca_name, f9_key.public_key(), ca_key, ca=True)
    leaf_name = name(module.SLOT_82_SUBJECT)
    leaf = cert(leaf_name, f9_name, slot_key.public_key(), f9_key,
                policy=b"\x03\x02", serial=22916048)
    pem = lambda c: c.public_bytes(serialization.Encoding.PEM)
    public_pem = slot_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    pin = root.fingerprint(hashes.SHA256()).hex()
    args = (pem(leaf), pem(f9), pem(root), [pem(ca)], public_pem)
    module.validate(*args, serial="22916048", trusted_root_sha256=pin)
    # Official 2025+ Yubico intermediate artifacts may contain several PEMs.
    unused = cert(name("unused intermediate"), root_name,
                  ec.generate_private_key(ec.SECP256R1()).public_key(), root_key, ca=True)
    module.validate(pem(leaf), pem(f9), pem(root), [pem(unused) + pem(ca)], public_pem,
                    serial="22916048", trusted_root_sha256=pin)
    attacks = [
        ("untrusted root", args, "00" * 32, "22916048"),
        ("wrong serial", args, pin, "23501671"),
        ("wrong public key", (pem(leaf), pem(f9), pem(root), [pem(ca)],
          root_key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)), pin, "22916048"),
        ("missing intermediate", (pem(leaf), pem(f9), pem(root), [], public_pem), pin, "22916048"),
        ("root bundle rejected", (pem(leaf), pem(f9), pem(root) + pem(ca), [pem(ca)], public_pem), pin, "22916048"),
        ("bad policy", (pem(cert(leaf_name, f9_name, slot_key.public_key(), f9_key,
                               policy=b"\x02\x02", serial=22916048)),
                        pem(f9), pem(root), [pem(ca)], public_pem), pin, "22916048"),
        ("wrong issuer signature", (pem(cert(leaf_name, f9_name, slot_key.public_key(), root_key,
                                            policy=b"\x03\x02", serial=22916048)),
                                    pem(f9), pem(root), [pem(ca)], public_pem), pin, "22916048"),
        ("expired leaf", (pem(cert(leaf_name, f9_name, slot_key.public_key(), f9_key,
                                   policy=b"\x03\x02", serial=22916048, valid=False)),
                          pem(f9), pem(root), [pem(ca)], public_pem), pin, "22916048"),
    ]
    rejected = 0
    for label, inputs, fingerprint, serial in attacks:
        try:
            module.validate(*inputs, serial=serial, trusted_root_sha256=fingerprint)
        except Exception:
            rejected += 1
        else:
            raise AssertionError("Accepted invalid attestation: " + label)
    print(f"PASS: synthetic root/F9/82 chain and {rejected} negative cases; no PC/SC access")
    print("NO-GO: no authentic Yubico attestation, no live AES256 or age decrypt")


if __name__ == "__main__":
    main()
