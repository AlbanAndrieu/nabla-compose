#!/usr/bin/env python3
"""Offline-safe dependency ordering for optional TrueNAS Catalog v2 Apps.

Uses only verified entityRef relations, never guesses identity from names.
Dependencies outside the selected wave must already be RUNNING.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def deferred_start_order(
    entries: dict[str, dict[str, Any]],
    states: dict[str, str],
    deferred: set[str],
) -> tuple[list[str], list[str]]:
    """Return (start order, dependency blockers) without querying or mutating TrueNAS.

    Only STOPPED Apps are considered start candidates. Ambiguous, absent,
    or inactive providers are blocking. Cycle detection is deterministic.
    """
    candidates = {app for app in deferred if states.get(app) == "STOPPED"}
    refs: dict[str, set[str]] = defaultdict(set)
    for app, row in entries.items():
        for ref in row.get("entityRefs", []):
            refs[ref].add(app)

    prerequisites: dict[str, set[str]] = {app: set() for app in candidates}
    blockers: set[str] = set()
    for app in sorted(candidates):
        row = entries.get(app)
        if row is None:
            blockers.add(f"{app}: missing inventory entry")
            continue
        for ref in sorted(set(row.get("dependsOn", []))):
            providers = refs.get(ref, set())
            if len(providers) != 1:
                reason = "missing" if not providers else "ambiguous"
                blockers.add(f"{app}: {reason} dependency provider for {ref}")
                continue
            provider = next(iter(providers))
            if provider == app:
                continue
            if provider in candidates:
                prerequisites[app].add(provider)
            elif states.get(provider) != "RUNNING":
                blockers.add(f"{app}: dependency {provider} is not RUNNING")

    order: list[str] = []
    ready = {app for app in candidates if not prerequisites[app]}
    while ready:
        app = min(ready)
        ready.remove(app)
        order.append(app)
        for dependent in candidates - set(order):
            if app in prerequisites[dependent]:
                prerequisites[dependent].remove(app)
                if not prerequisites[dependent]:
                    ready.add(dependent)
    if len(order) != len(candidates):
        blockers.add("cycle in deferred dependency graph")
    return order, sorted(blockers)


def core_dependency_blockers(
    entries: dict[str, dict[str, Any]],
    states: dict[str, str],
    core_order: list[str],
) -> list[str]:
    """Verify selected RUNNING core apps have verified, RUNNING providers.

    Do not infer app identities from entity names. If a dependency has no
    provider, multiple providers, or a provider that is not RUNNING, block
    the core wave before any stop/start operation.
    """
    ref_providers: dict[str, set[str]] = defaultdict(set)
    for app, entry in entries.items():
        for ref in entry.get("entityRefs", []):
            ref_providers[ref].add(app)

    blockers: set[str] = set()
    for app in sorted(set(core_order)):
        if states.get(app) != "RUNNING":
            blockers.add(f"{app}: selected core App is not RUNNING")
            continue
        entry = entries.get(app)
        if entry is None:
            blockers.add(f"{app}: missing inventory entry")
            continue
        for ref in sorted(set(entry.get("dependsOn", []))):
            providers = ref_providers.get(ref, set())
            if len(providers) != 1:
                reason = "missing" if not providers else "ambiguous"
                blockers.add(f"{app}: {reason} dependency provider for {ref}")
                continue
            provider = next(iter(providers))
            if states.get(provider) != "RUNNING":
                blockers.add(f"{app}: dependency {provider} is not RUNNING")
    return sorted(blockers)
