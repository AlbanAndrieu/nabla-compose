#!/usr/bin/env python3
"""Privacy boundary: never upload Nuclei raw HTTP data to public Actions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

HOST_RE = re.compile(r"^(?:82\.66\.4\.247|[a-z0-9.-]+\.albandrieu\.com)$")
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
LEVELS = {"info", "low", "medium", "high", "critical"}


def sanitize(source: Path, target: Path) -> int:
    if source.resolve() == target.resolve():
        raise ValueError("input must differ from output")
    count = 0
    with source.open(encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            item = json.loads(line)
            host = item.get("host")
            severity = item.get("info", {}).get("severity")
            template_id = item.get("template-id")
            if not (isinstance(host, str) and HOST_RE.fullmatch(host)
                    and severity in LEVELS and isinstance(template_id, str)
                    and ID_RE.fullmatch(template_id)):
                raise ValueError("unexpected Nuclei result; raw upload forbidden")
            row = {"host": host, "severity": severity, "template_id": template_id}
            matcher = item.get("matcher-name")
            if isinstance(matcher, str) and ID_RE.fullmatch(matcher):
                row["matcher"] = matcher
            dst.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("target", type=Path)
    args = cli.parse_args()
    print(f"minimized_findings={sanitize(args.source, args.target)}")
