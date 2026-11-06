"""Keep Prometheus exporter alerting aligned with Backstage operational state.

An exporter that is declared but not deployed yet must not page as
``NablaExporterTargetDown``. Its static target keeps the
``operational_state: planned`` label (the target stays scraped and visible as
down) only while the Backstage entity is ``planned``; deploying the exporter
requires switching the entity to ``active`` and removing the label together.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = ROOT / "apps" / "prometheus" / "prometheus.yml"
CORE_RULES = ROOT / "apps" / "prometheus" / "rules" / "nabla-core.rules.yml"

# Prometheus job -> (catalog-info.yaml, Backstage entity name)
EXPORTER_ENTITIES = {
    "postgres_exporter": ("apps/postgres/catalog-info.yaml", "postgres-exporter"),
    "haproxy": ("apps/haproxy-exporter/catalog-info.yaml", "haproxy-exporter"),
    "opensearch": ("apps/opensearch-exporter/catalog-info.yaml", "opensearch-exporter"),
    "opensearch-security": (
        "apps/opensearch-exporter/catalog-info.yaml",
        "opensearch-security-exporter",
    ),
}


def _operational_state(relative: str, name: str) -> str:
    for document in yaml.safe_load_all((ROOT / relative).read_text(encoding="utf-8")):
        metadata = (document or {}).get("metadata") or {}
        if metadata.get("name") == name:
            labels = metadata.get("labels") or {}
            return labels.get("albandrieu.com/operational-state", "active")
    raise AssertionError(f"{name} not found in {relative}")


def _target_states() -> dict[str, set[str]]:
    config = yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))
    states: dict[str, set[str]] = {}
    for job in config["scrape_configs"]:
        for static in job.get("static_configs") or []:
            labels = static.get("labels") or {}
            states.setdefault(job["job_name"], set()).add(
                labels.get("operational_state", "active")
            )
    return states


def test_planned_label_matches_backstage_operational_state() -> None:
    states = _target_states()
    for job, (relative, name) in EXPORTER_ENTITIES.items():
        declared = _operational_state(relative, name)
        expected = {"planned"} if declared == "planned" else {"active"}
        assert states.get(job) == expected, (job, declared, states.get(job))


def test_only_mapped_jobs_carry_the_planned_label() -> None:
    planned_jobs = {
        job for job, values in _target_states().items() if "planned" in values
    }
    assert planned_jobs <= set(EXPORTER_ENTITIES), planned_jobs


def test_exporter_down_alert_ignores_planned_targets() -> None:
    rules = yaml.safe_load(CORE_RULES.read_text(encoding="utf-8"))
    alerts = {
        rule["alert"]: rule
        for group in rules["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }
    expr = alerts["NablaExporterTargetDown"]["expr"]
    assert 'operational_state!="planned"' in expr
    for job in EXPORTER_ENTITIES:
        assert job in expr
