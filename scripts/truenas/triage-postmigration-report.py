#!/usr/bin/env python3
"""Classify a private TrueNAS migration report without printing its raw logs.

Read-only and offline. Never reads credentials, Docker state, or applications.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path('/mnt/cpool/var/nabla/migration-20261024')
SESSION_NAME = re.compile(r'session-[A-Za-z0-9]{8,24}\Z')
MAX_SUMMARY = 16 * 1024
MAX_LOG = 256 * 1024
PHASES = {
    'postmigration-catalog', 'postmigration-service-readiness',
    'postmigration-gatus', 'postmigration-prometheus', 'apisix-runtime',
}
STATUSES = {'PASS', 'FAIL', 'WARN', 'SKIP'}


def read_regular(path: Path, parent: Path, cap: int) -> str | None:
    """Reject symlinks, absolute escapes and oversized files before reading."""
    if path.parent != parent or path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size > cap:
            return None
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def classify(phase: str, state: str, log: str | None) -> dict:
    """Use allowlisted static labels; never quote arbitrary log content."""
    if state == 'PASS':
        return {'category': 'passed', 'evidence': {}}
    if state == 'SKIP':
        return {'category': 'not_executed', 'evidence': {}}
    if log is None:
        return {'category': 'log_unavailable', 'evidence': {}}
    low = log.lower()
    evidence: dict[str, int] = {}
    if phase == 'postmigration-gatus':
        for line in log.splitlines()[:256]:
            if not line.startswith('{') or len(line) > 4096:
                continue
            try:
                data = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict) or data.get('source') not in {
                'gatus_lan_read_only', 'gatus_saved_snapshot'
            }:
                continue
            for key in ('declared', 'runtime', 'up', 'down', 'unverified'):
                value = data.get(key)
                if type(value) is int and 0 <= value <= 512:
                    evidence[key] = value
            break
        if evidence.get('down', 0):
            return {'category': 'observed_monitors_down', 'evidence': evidence}
        return {'category': 'gatus_samples_missing_or_unverified', 'evidence': evidence}
    if phase == 'postmigration-catalog':
        if re.search(r'drift|mismatch|out.of.date|not up.to.date|different from|differs', low):
            category = 'generated_catalog_drift'
        elif re.search(r'no such file|missing|file not found', low):
            category = 'catalog_input_missing'
        else:
            category = 'catalog_check_failed'
    elif phase == 'postmigration-service-readiness':
        if re.search(r'unhealthy|healthcheck|health.check|restarting', low):
            category = 'runtime_or_healthcheck_failed'
        elif re.search(r'connection refused|timed out|timeout', low):
            category = 'functional_connection_failed'
        else:
            category = 'functional_readiness_failed'
    elif phase == 'postmigration-prometheus':
        if re.search(r'runtime=(restarting|exited|dead|created|unknown)', low):
            category = 'prometheus_runtime_unavailable'
        elif re.search(r'config differs|config drift|promtool rejected|configuration problem', low):
            category = 'prometheus_config_or_rules'
        elif re.search(r'target_not_up=[1-9]|targets are not up|unhealthy targets|active.targets.*unavailable|target api unavailable|one or more prometheus targets are not up', low):
            category = 'prometheus_scrape_degraded'
        else:
            category = 'prometheus_validation_failed'
    elif phase == 'apisix-runtime':
        if re.search(r'not_deployed_or_ambiguous|unverified|config=unverified', low):
            category = 'optional_gateway_unverified'
        elif re.search(r'runtime=failed', low):
            category = 'gateway_container_failed'
        else:
            category = 'gateway_diagnostic_incomplete'
    else:
        category = 'unclassified'
    return {'category': category, 'evidence': evidence}


def analyze(session: Path, root: Path = ROOT) -> dict:
    """Require an exact session descendant, never follow private-file symlinks."""
    if (not SESSION_NAME.fullmatch(session.name) or session.parent != root
            or session.is_symlink() or not session.is_dir()):
        raise ValueError('invalid_session_location')
    summary = read_regular(session / 'summary.tsv', session, MAX_SUMMARY)
    if summary is None:
        raise ValueError('private_summary_unavailable')
    rows = list(csv.reader(summary.splitlines(), delimiter='\t'))
    if not rows or rows[0] != ['phase', 'result', 'log'] or len(rows) > 65:
        raise ValueError('invalid_summary_format')
    checks = []
    seen = set()
    for row in rows[1:]:
        if len(row) != 3:
            raise ValueError('invalid_summary_row')
        phase, state, location = row
        if phase not in PHASES or state not in STATUSES or phase in seen:
            raise ValueError('invalid_summary_phase')
        seen.add(phase)
        log_path = Path(location)
        # The runner writes absolute paths under the same report session.
        # Fail closed on relative paths, symlinks, or unexpected filenames.
        if not log_path.is_absolute() or log_path.name != f'{phase}.log':
            log = None
        else:
            log = read_regular(log_path, session, MAX_LOG)
        checks.append({'phase': phase, 'state': state, **classify(phase, state, log)})
    if not checks:
        raise ValueError('empty_summary')
    failed = sum(x['state'] == 'FAIL' for x in checks)
    uncertain = sum(x['state'] in ('WARN', 'SKIP') for x in checks)
    return {'phase_count': len(checks), 'failed': failed,
            'unverified': uncertain, 'checks': checks,
            'complete': failed == 0 and uncertain == 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--session', type=Path, required=True)
    args = parser.parse_args()
    if not args.check:
        parser.error('only --check is supported')
    try:
        result = analyze(args.session)
    except ValueError:
        print('INCOMPLETE: private diagnostic session invalid or unavailable')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 1 if result['failed'] else (2 if result['unverified'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
