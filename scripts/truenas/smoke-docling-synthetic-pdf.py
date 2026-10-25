#!/usr/bin/env python3
"""Bounded synthetic-PDF conversion smoke; never reads private documents.

--check validates a PDF fixture offline. --apply POSTs only to LAN Docling.
Neither mode submits an OpenRAG ingestion or mutates an OpenSearch index.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

DOCLING_URL = "http://172.17.0.24:5001"
SENTINEL = "NABLA_SYNTHETIC_DOCLING_280_X7Q9"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 16 * 1024


def synthetic_pdf() -> bytes:
    """Generate one tiny, valid, self-contained PDF (no filesystem reads)."""
    contents = f"BT /F1 14 Tf 48 750 Td ({SENTINEL}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        b"<< /Length " + str(len(contents)).encode("ascii") + b" >>\nstream\n" + contents + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def multipart_request(pdf: bytes) -> Request:
    if pdf != synthetic_pdf() or len(pdf) > MAX_PDF_BYTES:
        raise ValueError("invalid synthetic fixture")
    boundary = "NablaDocling280SyntheticBoundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="nabla-synthetic-280.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("ascii") + pdf + f"\r\n--{boundary}\r\n".encode("ascii")
    body += (b'Content-Disposition: form-data; name="to_formats"\r\n\r\nmd\r\n'
             + f"--{boundary}--\r\n".encode("ascii"))
    return Request(
        DOCLING_URL + "/v1/convert/file",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/json"},
        method="POST",
    )


def conversion_accepted(raw: bytes) -> bool:
    """Require successful parsing and actual extraction of the sentinel."""
    if len(raw) > MAX_RESPONSE_BYTES:
        return False
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return False
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return False
    document = payload.get("document")
    if not isinstance(document, dict):
        return False
    return any(
        SENTINEL in value
        for name in ("md_content", "text_content")
        if isinstance((value := document.get(name)), str)
    )


def apply_conversion() -> str:
    """Upload exactly one synthetic document; return a redacted result label."""
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(DOCLING_URL + "/ready", timeout=8) as response:
            if response.status != 200:
                return "DOC_LING_NOT_READY"
        with opener.open(multipart_request(synthetic_pdf()), timeout=180) as response:
            if response.status != 200:
                return "CONVERSION_HTTP_NON_200"
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        return "HTTP_" + str(exc.code)
    except (URLError, TimeoutError, OSError):
        return "LAN_TRANSPORT_UNAVAILABLE"
    return "CONVERSION_PASS" if conversion_accepted(raw) else "CONVERSION_UNVERIFIED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    fixture = synthetic_pdf()
    if (not fixture.startswith(b"%PDF-1.4\n") or
            SENTINEL.encode("ascii") not in fixture or
            len(fixture) > MAX_PDF_BYTES):
        print("FAIL: synthetic_pdf_fixture_invalid")
        return 2
    if args.check:
        print("PASS: synthetic_pdf_fixture_offline")
        print("NOT_TESTED: Docling_conversion_OpenRAG_ingestion_retrieval")
        return 0
    outcome = apply_conversion()
    print("PASS: docling_synthetic_conversion" if outcome == "CONVERSION_PASS"
          else "UNVERIFIED: docling_synthetic_conversion=" + outcome)
    print("NOT_TESTED: OpenRAG_ingestion_OpenSearch_indexing_retrieval")
    return 0 if outcome == "CONVERSION_PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
