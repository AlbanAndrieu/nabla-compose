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


def _php_fpm_verdict(ps_lines: str, tmp_path: Path) -> str:
    """Run the collector's PHP-FPM block against a stubbed ``ps``."""
    source = AUDIT.read_text(encoding="utf-8")
    block = 'if fpm_output="$(ps axww' + source.split('if fpm_output="$(ps axww', 1)[1]
    block = block.split("if [ -r /usr/local/lib/php-fpm.conf ]", 1)[0]
    ps_stub = tmp_path / "ps"
    ps_stub.write_text(f"#!/bin/sh\ncat <<'PS'\n{ps_lines}\nPS\n", encoding="utf-8")
    ps_stub.chmod(0o755)
    script = "emit() { printf '%s %s %s\\n' \"$1\" \"$2\" \"$3\"; }\n" + block
    result = subprocess.run(["sh", "-c", script], capture_output=True, text=True,
                            timeout=10, check=True,
                            env={"PATH": f"{tmp_path}:/usr/bin:/bin"})
    return next(line for line in result.stdout.splitlines()
                if "php_fpm.nginx_workers" in line)


def test_php_fpm_idle_ondemand_pool_is_healthy(tmp_path):
    master = " 9000 php-fpm: master process (/usr/local/lib/php-fpm.conf)"
    worker = " 40000 php-fpm: pool nginx (php-fpm)"
    assert _php_fpm_verdict(master, tmp_path).startswith("PASS php_fpm.nginx_workers 0")
    assert _php_fpm_verdict(f"{master}\n{worker}\n{worker}", tmp_path).startswith(
        "PASS php_fpm.nginx_workers 2")
    assert _php_fpm_verdict("\n".join([master] + [worker] * 5), tmp_path).startswith(
        "WARN php_fpm.nginx_workers 5")
    assert _php_fpm_verdict(" 100 nginx: worker process", tmp_path).startswith(
        "WARN php_fpm.nginx_workers 0")
