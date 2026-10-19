"""Offline security boundaries for selected Site Alban -> private DefectDojo reports."""

from __future__ import annotations

import importlib.util
import json
from xml.etree import ElementTree
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "scripts/security/pull-site-alban-security-report.py"
)
SPEC = importlib.util.spec_from_file_location("site_alban_security_report", SOURCE)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_only_successful_master_runs_are_trusted() -> None:
    run = {
        "name": "Supply Chain Security (Trivy)",
        "head_branch": "master",
        "conclusion": "success",
        "event": "schedule",
        "head_sha": "a" * 40,
    }
    assert module.allowed_artifact("trivy", run, 123) == "trivy-master-" + "a" * 40
    with pytest.raises(SystemExit):
        module.allowed_artifact("trivy", {**run, "head_branch": "feature"}, 123)
    with pytest.raises(SystemExit):
        module.allowed_artifact("trivy", {**run, "conclusion": "failure"}, 123)
    with pytest.raises(SystemExit):
        module.allowed_artifact("trivy", {**run, "name": "Unrelated job"}, 123)


def test_trivy_only_high_and_critical_vulnerabilities() -> None:
    payload = {
        "SchemaVersion": 2,
        "Results": [
            {
                "Target": "package-lock.json",
                "Vulnerabilities": [
                    {"VulnerabilityID": "HIGH-1", "Severity": "HIGH"},
                    {"VulnerabilityID": "LOW-1", "Severity": "LOW"},
                    {"VulnerabilityID": "CRIT-1", "Severity": "CRITICAL"},
                ],
                "Misconfigurations": [{"ID": "ignored"}],
                "Licenses": [{"Name": "reviewed separately"}],
            }
        ],
    }
    filtered = json.loads(module.filter_findings("trivy", json.dumps(payload).encode()))
    item = filtered["Results"][0]
    assert [finding["VulnerabilityID"] for finding in item["Vulnerabilities"]] == [
        "HIGH-1", "CRIT-1"
    ]
    assert "Licenses" not in item
    assert "Misconfigurations" not in item


def test_nuclei_filters_to_high_or_critical() -> None:
    rows = [
        {"info": {"severity": "low"}, "template-id": "L"},
        {"info": {"severity": "high"}, "template-id": "H"},
        {"info": {"severity": "critical"}, "template-id": "C"},
    ]
    payload = "\n".join(json.dumps(row) for row in rows).encode()
    filtered = module.filter_findings("nuclei", payload).decode().splitlines()
    assert [json.loads(row)["template-id"] for row in filtered] == ["H", "C"]


def test_zap_only_accepts_pre_minimized_high_alerts() -> None:
    payload = {"site": [{"@name": "https://www.albanandrieu.com",
                        "alerts": [{"riskcode": "3", "pluginid": "10035",
                                    "alert": "ZAP passive rule 10035"}]}]}
    xml = module.filter_findings("zap", json.dumps(payload).encode())
    report = ElementTree.fromstring(xml)
    assert report.findtext("./site/alerts/alertitem/pluginid") == "10035"
    assert report.findtext("./site/alerts/alertitem/riskcode") == "3"
    payload["site"][0]["alerts"][0]["instances"] = [{"uri": "/private?token=SECRET"}]
    with pytest.raises(SystemExit):
        module.filter_findings("zap", json.dumps(payload).encode())


def test_bounded_report_size_is_fail_closed() -> None:
    with pytest.raises(SystemExit):
        module.filter_findings("nuclei", b"x" * (module.MAX_REPORT_BYTES + 1))
