#!/usr/bin/env python3
"""Compare the versioned Site Alban OPML to FreshRSS selection without any network."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]


def urls_from_opml(path: Path) -> set[str]:
    tree = ElementTree.parse(path)
    if tree.getroot().tag != "opml":
        raise ValueError("Expected OPML document")
    urls = [node.get("xmlUrl") for node in tree.iter("outline") if node.get("xmlUrl")]
    if not urls or len(urls) != len(set(urls)):
        raise ValueError("Empty or duplicate OPML URLs")
    if any(urlsplit(url).scheme != "https" for url in urls):
        raise ValueError("Non-HTTPS OPML URL")
    return set(urls)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-opml", type=Path, default=ROOT / "apps/nabla-site-alban/data/security/security-feeds.opml")
    parser.add_argument("--freshrss-json", type=Path, default=ROOT / "config/freshrss/security-sources.json")
    parser.add_argument("--strict", action="store_true", help="Fail when FreshRSS contains URLs absent from Site Alban")
    args = parser.parse_args()
    site = urls_from_opml(args.site_opml)
    sources = json.loads(args.freshrss_json.read_text(encoding="utf-8"))["sources"]
    fresh = {source["url"] for source in sources}
    shared = fresh & site
    extra = fresh - site
    print(f"site={len(site)} freshrss={len(fresh)} shared={len(shared)} freshrss_only={len(extra)}")
    for url in sorted(extra):
        print(f"FRESHRSS_ONLY {url}")
    print("No subscriptions changed. Use --strict only after source ownership is reconciled.")
    return int(args.strict and bool(extra))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, ElementTree.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
