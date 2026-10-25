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
    if state == 'SKIP':
        return {'category': 'not_executed', 'evidence': {}}
    if log is None:
        return {'category': 'log_unavailable', 'evidence': {}}
    if state == 'PASS':
        return {'category': 'passed', 'evidence': {}}
    low = log.lower()
    evidence: dict[str, object] = {}
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
        # generator emits "stale catalog-v2 artifacts:" for actual drift;
        # absence of the token does not prove that a generated file is stale.
        if 'stale catalog-v2 artifacts:' in low:
            category = 'generated_catalog_drift'
            # Count generator list entries only; never copy file paths.
            items = [line for line in log.splitlines()[:128]
                     if line.startswith(' - ') and len(line) <= 320]
            evidence['stale_artifact_count'] = min(len(items), 64)
            allowed = {'catalog/generated/entities.json',
                       'catalog/generated/homelab.cdx.json',
                       'catalog/generated/identity-map.json'}
            # No raw operator paths; only canonical generated artifacts.
            artifacts = sorted({
                line[3:].strip() for line in items
                if line.startswith(' - ') and line[3:].strip() in allowed
            })
            if artifacts:
                evidence['stale_artifacts'] = artifacts
        elif re.search(r'modulenotfounderror|importerror|no module named', low):
            category = 'catalog_generator_dependency_error'
        elif re.search(r'no such file|file not found', low):
            category = 'catalog_input_missing'
        elif re.search(r'drift|mismatch|out.of.date|not up.to.date|different from|differs', low):
            category = 'generated_catalog_drift'
        else:
            category = 'catalog_check_failed'
    elif phase == 'postmigration-service-readiness':
        # Parse only an explicitly allowlisted service/status pair from the
        # stable readiness report. All other text is untrusted diagnostics.
        allowed = {'gatus', 'litellm', 'openrag', 'scrutiny', 'influxdb',
                   'prometheus', 'sentry', 'sample'}
        affected = []
        for line in log.splitlines()[:200]:
            match = re.match(r'^\s*(BLOCKED|DEGRADED|UNKNOWN|WARN)\s+'
                             r'([a-z0-9-]+)\s+TrueNAS=', line)
            if match and match.group(2) in allowed and match.group(2) not in (
                    item['service'] for item in affected):
                affected.append({'service': match.group(2),
                                 'status': match.group(1)})
        evidence['affected_count'] = len(affected)
        if affected:
            evidence['affected_services'] = affected
            reasons: dict[str, list[str]] = {}
            service = None
            selected = {row['service'] for row in affected}
            # Runner renders a service heading then up to 3 indented
            # notes. Only fixed categories may leave this private report.
            for line in log.splitlines()[:200]:
                header = re.match(
                    r'^\s*(?:BLOCKED|DEGRADED|UNKNOWN|WARN)\s+'
                    r'([a-z0-9-]+)\s+TrueNAS=', line)
                if header:
                    service = header.group(1) if header.group(1) in selected else None
                    continue
                note = re.match(r'^\s+·\s+(.+)
        # A plain 'no Docker healthcheck' note is informational and must
        # not convert an unrelated HTTP failure into a healthcheck failure.
        if re.search(r'docker unhealthy|healthcheck (?:permissions|binary|'
                     r'connectivity|http response|nonzero|unhealthy)|\brestarting\b', low):
            category = 'runtime_or_healthcheck_failed'
        elif re.search(r'connection refused|timed out|timeout|http probe unavailable', low):
            category = 'functional_connection_failed'
        else:
            category = 'functional_readiness_failed'
    elif phase == 'postmigration-prometheus':
        # "=== Prometheus config drift ===" is an unconditional SECTION
        # HEADER in diagnose-prometheus-targets.sh; never treat it as drift.
        # Only explicit failure messages can establish the cause.
        metrics = re.search(r'(?m)^prometheus_runtime=running\s+'
                            r'config_validation=(passed|invalid_or_unverified)\s+'
                            r'target_up=(\d+)\s+target_not_up=(\d+)\s*$', log)
        if metrics:
            up, not_up = int(metrics.group(2)), int(metrics.group(3))
            if up <= 512 and not_up <= 512:
                evidence.update({'target_up': up, 'target_not_up': not_up})
        runtime_down = bool(re.search(
            r'(?m)^.*Prometheus runtime=(restarting|exited|dead|created|unknown)\b', log))
        config_bad = bool(re.search(
            r'host prometheus config differs|promtool rejected the config|'
            r'cannot read /etc/prometheus/prometheus.yml from container|'
            r'prometheus_rules_permission_denied|prometheus_config_permission_denied',
            low))
        targets_down = bool(re.search(
            r'(?m)^Unhealthy targets\b|one or more Prometheus targets are not UP|'
            r'one or more declared Prometheus jobs are absent|'
            r'evidence=collector_targets_degraded_not_prometheus_startup', log,
            flags=re.IGNORECASE)) or evidence.get('target_not_up', 0) > 0
        api_unreachable = bool(re.search(
            r'Prometheus active-target API unavailable', log, flags=re.IGNORECASE))
        signals = []
        if runtime_down:
            signals.append('runtime_unavailable')
        if config_bad:
            signals.append('configuration_or_rules')
        if targets_down:
            signals.append('scrape_targets_degraded')
        if api_unreachable:
            signals.append('targets_api_unavailable')
        if signals:
            evidence['signals'] = signals
        if runtime_down:
            category = 'prometheus_runtime_unavailable'
        elif config_bad:
            category = 'prometheus_config_or_rules'
        elif targets_down:
            category = 'prometheus_scrape_degraded'
        elif api_unreachable:
            category = 'prometheus_api_unavailable'
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
    uncertain = sum(x['state'] in ('WARN', 'SKIP') or
                    x['category'] == 'log_unavailable' for x in checks)
    expected_postmigration = PHASES - {'apisix-runtime'}
    observed = set(seen)
    missing_phases = sorted((expected_postmigration - observed)
                            if observed != {'apisix-runtime'} else set())
    if missing_phases or (observed - expected_postmigration and
                          observed != {'apisix-runtime'}):
        uncertain += 1
    return {'phase_count': len(checks), 'failed': failed,
            'unverified': uncertain, 'missing_phases': missing_phases,
            'checks': checks, 'complete': failed == 0 and uncertain == 0}


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
, line)
                if not note:
                    service = None
                    continue
                if service is None:
                    continue
                value = note.group(1).lower()
                code = None
                if re.search(r'\bmonitors=\d+\s+up=\d+\s+down=\d+', value):
                    code = 'monitor_coverage_degraded'
                elif 'http probe unavailable' in value:
                    code = 'http_probe_unavailable'
                elif 'running git sha not attested' in value or 'git provenance endpoint unavailable' in value:
                    code = 'build_provenance_unverified'
                elif 'docker unhealthy' in value:
                    code = 'docker_unhealthy'
                elif re.search(r'truenas (?:stopped|crashed|error|missing)', value):
                    code = 'truenas_lifecycle_failure'
                elif 'state unknown' in value:
                    code = 'container_state_unverified'
                elif 'gatus' in value and re.search(r'config|gid 568|group', value):
                    code = 'gatus_config_access_unverified'
                elif 'no docker healthcheck' in value:
                    code = 'no_docker_healthcheck'
                if code:
                    codes = reasons.setdefault(service, [])
                    if code not in codes and len(codes) < 3:
                        codes.append(code)
            if reasons:
                evidence['service_reasons'] = reasons
        # A plain 'no Docker healthcheck' note is informational and must
        # not convert an unrelated HTTP failure into a healthcheck failure.
        if re.search(r'docker unhealthy|healthcheck (?:permissions|binary|'
                     r'connectivity|http response|nonzero|unhealthy)|\brestarting\b', low):
            category = 'runtime_or_healthcheck_failed'
        elif re.search(r'connection refused|timed out|timeout|http probe unavailable', low):
            category = 'functional_connection_failed'
        else:
            category = 'functional_readiness_failed'
    elif phase == 'postmigration-prometheus':
        # "=== Prometheus config drift ===" is an unconditional SECTION
        # HEADER in diagnose-prometheus-targets.sh; never treat it as drift.
        # Only explicit failure messages can establish the cause.
        metrics = re.search(r'(?m)^prometheus_runtime=running\s+'
                            r'config_validation=(passed|invalid_or_unverified)\s+'
                            r'target_up=(\d+)\s+target_not_up=(\d+)\s*$', log)
        if metrics:
            up, not_up = int(metrics.group(2)), int(metrics.group(3))
            if up <= 512 and not_up <= 512:
                evidence.update({'target_up': up, 'target_not_up': not_up})
        runtime_down = bool(re.search(
            r'(?m)^.*Prometheus runtime=(restarting|exited|dead|created|unknown)\b', log))
        config_bad = bool(re.search(
            r'host prometheus config differs|promtool rejected the config|'
            r'cannot read /etc/prometheus/prometheus.yml from container|'
            r'prometheus_rules_permission_denied|prometheus_config_permission_denied',
            low))
        targets_down = bool(re.search(
            r'(?m)^Unhealthy targets\b|one or more Prometheus targets are not UP|'
            r'one or more declared Prometheus jobs are absent|'
            r'evidence=collector_targets_degraded_not_prometheus_startup', log,
            flags=re.IGNORECASE)) or evidence.get('target_not_up', 0) > 0
        api_unreachable = bool(re.search(
            r'Prometheus active-target API unavailable', log, flags=re.IGNORECASE))
        signals = []
        if runtime_down:
            signals.append('runtime_unavailable')
        if config_bad:
            signals.append('configuration_or_rules')
        if targets_down:
            signals.append('scrape_targets_degraded')
        if api_unreachable:
            signals.append('targets_api_unavailable')
        if signals:
            evidence['signals'] = signals
        if runtime_down:
            category = 'prometheus_runtime_unavailable'
        elif config_bad:
            category = 'prometheus_config_or_rules'
        elif targets_down:
            category = 'prometheus_scrape_degraded'
        elif api_unreachable:
            category = 'prometheus_api_unavailable'
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
    uncertain = sum(x['state'] in ('WARN', 'SKIP') or
                    x['category'] == 'log_unavailable' for x in checks)
    expected_postmigration = PHASES - {'apisix-runtime'}
    observed = set(seen)
    missing_phases = sorted((expected_postmigration - observed)
                            if observed != {'apisix-runtime'} else set())
    if missing_phases or (observed - expected_postmigration and
                          observed != {'apisix-runtime'}):
        uncertain += 1
    return {'phase_count': len(checks), 'failed': failed,
            'unverified': uncertain, 'missing_phases': missing_phases,
            'checks': checks, 'complete': failed == 0 and uncertain == 0}


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
