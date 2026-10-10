#!/usr/bin/env python3
"""Read-only DSOMM post-reboot contract: served YAML must be actual assessment data."""
from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

ASSETS = {
    "meta.yaml": ("teams",),
    "default/model.yaml": ("meta",),
    "team-progress.yaml": ("progress",),
    "team-evidence.yaml": ("evidence",),
}
CONTEXTS = {"Nabla Platform", "Nabla Applications"}


def probe(base_url: str, *, timeout: float = 8.0) -> None:
    payloads = {}
    for path, required in ASSETS.items():
        url = f"{base_url.rstrip('/')}/assets/YAML/{path}"
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            raw = response.read(1024 * 1024 + 1)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
        if status != 200 or not raw or len(raw) > 1024 * 1024:
            raise ValueError(f"{path}: unexpected HTTP={status} or asset size={len(raw)}")
        # Caddy may provide no YAML content-type, so validate actual document.
        if b"<html" in raw[:512].lower() or "text/html" in content_type.lower():
            raise ValueError(f"{path}: HTML fallback returned instead of YAML")
        # The pinned model may be a multi-document YAML stream.
        documents = list(yaml.safe_load_all(raw))
        if not documents or any(not isinstance(doc, dict) for doc in documents):
            raise ValueError(f"{path}: malformed YAML document stream")
        matches = [doc for doc in documents if all(key in doc for key in required)]
        if len(matches) != 1:
            raise ValueError(f"{path}: expected exactly one matching YAML document")
        data = matches[0]
        if path == "default/model.yaml":
            if str(data["meta"].get("version")) != "5.0.2":
                raise ValueError(f"{path}: unexpected DSOMM model version")
            if len(documents) < 2 or not any(
                "Agentic AI" in doc or "Build and Deployment" in doc
                for doc in documents[1:]
            ):
                raise ValueError(f"{path}: missing DSOMM activities document")
        payloads[path] = data
        print(f"OK asset={path} http=200 bytes={len(raw)}")
    contexts = set(payloads["meta.yaml"]["teams"])
    if not CONTEXTS.issubset(contexts):
        raise ValueError("DSOMM contexts missing from meta.yaml")
    progress = payloads["team-progress.yaml"]["progress"]
    evidence = payloads["team-evidence.yaml"]["evidence"]
    if not isinstance(progress, dict) or not progress:
        raise ValueError("DSOMM progression is empty")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("DSOMM evidence is empty")
    for context in CONTEXTS:
        if not any(isinstance(v, dict) and context in v for v in progress.values()):
            raise ValueError(f"DSOMM has no progress for {context}")
    print(f"OK dsomm HTTP YAML acceptance: progress_activities={len(progress)} evidence_activities={len(evidence)} contexts=2")


def browser_probe(base_url: str) -> bool:
    """Optional browser-level smoke; never silently claim it ran."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        print("WARN DSOMM browser smoke not executed: playwright unavailable")
        return False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{base_url.rstrip('/')}/circular-heatmap", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1200)
            svg_count = page.locator("svg").count()
            print(f"INFO circular-heatmap svg_count={svg_count}")
            if not svg_count:
                raise ValueError("DSOMM circular-heatmap SVG was not rendered")
        finally:
            browser.close()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://172.17.0.24:31088")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--require-browser", action="store_true")
    args = parser.parse_args()
    try:
        probe(args.url)
        if args.browser or args.require_browser:
            if not browser_probe(args.url) and args.require_browser:
                raise ValueError("browser smoke is required but Playwright is unavailable")
    except (ValueError, HTTPError, URLError, TimeoutError, yaml.YAMLError, OSError) as exc:
        print(f"FAIL dsomm post-reboot acceptance: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
