#!/usr/bin/env python3
"""Dependency-ordered, read-only TrueNAS services runtime diagnostics."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
COLORS = {"green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m", "blue": "\033[36m"}


def render(state: str, name: str, detail: str, *, color: bool) -> None:
    icons = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}
    tone = {"pass": "green", "fail": "red", "warn": "yellow", "skip": "blue"}[state]
    message = f"{icons[state]} {state.upper():4} {name}: {detail}"
    print(f"{COLORS[tone]}{message}\033[0m" if color else message)


def probe(monitoring: dict, timeout: float) -> tuple[bool, str]:
    kind = str(monitoring.get("type") or "").lower()
    host = monitoring.get("host")
    port = monitoring.get("port")
    if not isinstance(host, str) or not host or not isinstance(port, int) or not 1 <= port <= 65535:
        return False, "missing host/port metadata"
    try:
        if kind in {"port", "tcp"}:
            with socket.create_connection((host, port), timeout=timeout):
                return True, f"TCP {host}:{port} reachable"
        if kind in {"http", "https"}:
            path = str(monitoring.get("path") or "/")
            if not path.startswith("/") or path.startswith("//"):
                return False, "invalid monitoring path"
            url = f"{kind}://{host}:{port}{path}"
            with urlopen(url, timeout=timeout) as response:  # noqa: S310
                status = response.status
            return 200 <= status < 400, f"HTTP {status}"
    except (OSError, HTTPError, URLError, TimeoutError) as exc:
        return False, f"{kind} probe failed: {type(exc).__name__}"
    return False, f"monitoring type {kind or 'absent'} unsupported"


def audit(apps: list[dict], plan: dict, topology: dict, *, deep: bool, color: bool, timeout: float) -> int:
    by_id = {str(item["id"]): item for item in apps}
    nodes = topology.get("nodes", [])
    entries = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    errors = warnings = passed = skipped = 0
    stopped = sorted(a for a, record in by_id.items() if record.get("state") == "STOPPED")
    selected = set(plan["selected_apps"])
    predecessors: dict[str, set[str]] = {name: set() for name in selected}
    for edge in plan.get("required_edges", []):
        before, after = edge["before"], edge["after"]
        if after in predecessors:
            predecessors[after].add(before)

    # Catalog app IDs are explicit where possible; the planner is canonical
    # for ordering and for resolving mapping from logical service IDs.
    monitoring_by_app: dict[str, list[tuple[str, dict]]] = {}
    for name, node in entries.items():
        runtime = node.get("runtime") or {}
        app = runtime.get("appId")
        if not app:
            source = str(node.get("sourcePath") or "")
            parts = Path(source).parts
            if len(parts) >= 2 and parts[0] == "apps":
                app = parts[1]
        if app in selected and isinstance(node.get("monitoring"), dict):
            monitoring_by_app.setdefault(app, []).append((name, node["monitoring"]))

    states: dict[str, str] = {}
    for i, wave in enumerate(plan["start_waves"], 1):
        phase = plan.get("start_wave_phases", [])[i - 1]
        print(f"\n🔗 Wave {i} · {phase} · {len(wave)} Apps")
        for name in wave:
            state = by_id[name].get("state", "UNKNOWN")
            blockers = sorted(parent for parent in predecessors[name] if states.get(parent) == "fail")
            if blockers:
                render("warn", name, f"required dependency failed: {', '.join(blockers)}", color=color)
                warnings += 1
            if state != "RUNNING":
                render("fail", name, f"TrueNAS app state={state}", color=color)
                states[name] = "fail"
                errors += 1
                continue
            checks = monitoring_by_app.get(name, [])
            if not deep or not checks:
                render("pass", name, "TrueNAS RUNNING" + ("; no declared network probe" if deep else ""), color=color)
                passed += 1
                states[name] = "pass"
                continue
            results = [(node, *probe(monitor, timeout)) for node, monitor in checks]
            failures = [f"{node} ({detail})" for node, ok, detail in results if not ok]
            if failures:
                # An unsupported/missing metadata check is not runtime proof of DOWN.
                render("warn", name, "; ".join(failures[:3]), color=color)
                warnings += 1
                states[name] = "warn"
            else:
                render("pass", name, f"RUNNING; {len(results)} network checks OK", color=color)
                passed += 1
                states[name] = "pass"

    print(f"\n⏹️  Intentional/non-selected STOPPED Apps: {len(stopped)}")
    if stopped:
        print("   " + ", ".join(stopped))
    for name in plan.get("unmapped_apps", []):
        render("warn", name, "no declared service-topology mapping", color=color)
        warnings += 1
    print(f"\n📊 SUMMARY apps_ok={passed} failures={errors} warnings={warnings} stopped={len(stopped)}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apps", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--topology", type=Path, default=ROOT / "catalog/service-topology.json")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()
    if not 0 < args.timeout <= 15:
        parser.error("timeout must be within (0, 15] seconds")
    return audit(
        json.loads(args.apps.read_text()),
        json.loads(args.plan.read_text()),
        json.loads(args.topology.read_text()),
        deep=args.deep,
        color=not args.no_color and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
