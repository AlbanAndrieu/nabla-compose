"""Offline checks for pfSense posture configuration + read-only runtime auditing."""
from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts/pfsense/audit-posture.sh"
DIAGNOSE = ROOT / "scripts/pfsense/diagnose-recover.sh"
ROADMAP = ROOT / "docs/roadmap.md"


def test_posture_entrypoints_are_valid_bash():
    for path in (AUDIT, DIAGNOSE):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True,
                                text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr


def test_check_posture_alone_reuses_read_only_audit():
    source = DIAGNOSE.read_text(encoding="utf-8")
    block = source.split('if [[ -n "${POSTURE_ACTION}" ]]; then', 1)[1].split("\nfi", 1)[0]
    assert 'if [[ "${POSTURE_ACTION}" == "check" ]]; then' in block
    assert 'bash "${SCRIPT_DIR}/audit-posture.sh" "${posture_args[@]}"' in block
    assert 'posture_args+=(--port "${SSH_PORT}")' in block
    assert 'run_posture_admin "${POSTURE_ACTION}"' in block


def test_dnsbl_asn_snort_and_php_fpm_have_independent_evidence():
    source = AUDIT.read_text(encoding="utf-8")
    for needle in ("pfblocker.dnsbl_loaded_entries", "pfblocker.dnsbl_staged_lines",
                   "service.snort", "xml_value asn_reporting", "pfblocker.asn_reporting",
                   "php_fpm.nginx_workers", "php_fpm.nginx_rss_kib",
                   "php_fpm.generated_profile", "4/30/1/2/500"):
        assert needle in source
    assert "service snort restart" not in source


def test_h07_does_not_claim_runtime_accepted():
    source = ROADMAP.read_text(encoding="utf-8")
    h07 = source.split("### H07 — pfSense", 1)[1].split("\n## ", 1)[0]
    for needle in ("DNSBL", "ASN reporting", "Snort", "7 workers",
                   "280 Mio", "24/10", "4/30/1/2/500", "NOT_VERIFIED"):
        assert needle in h07
