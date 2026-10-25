#!/usr/bin/env python3
"""Offline, read-only triage of private TrueNAS migration sessions.

Output contains only allowlisted categories and bounded blocker COUNTS;
never copies secret values, application names, source paths or raw logs.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path('/mnt/cpool/var/nabla/migration-20261024')
SESSION = re.compile(r'session-[A-Za-z0-9]{8,24}\Z')
WAVES = ('core', 'gatus', 'deferred')
PHASES = frozenset({
    'catalog-core', 'catalog-gatus', 'catalog-deferred',
    'canonical-secret-files', 'first-wave-env', 'openrag-env-migration',
    'akvorado-env-migration', 'openrag-backstage-bundle',
    'openrag-opensearch-secret', 'vaultwarden-inventory',
    'postmigration-catalog', 'postmigration-service-readiness',
    'postmigration-gatus', 'postmigration-prometheus',
    'prometheus-targets', 'prometheus-config-access',
    'prometheus-rules-access', 'openrag-startup',
    'openrag-dependencies', 'ai-runtime-recovery',
    'openrag-opensearch-legacy-secret', 'sentry-consumers',
    'sentry-recovery-preflight', 'akvorado-config',
    'akvorado-blocked', 'akvorado-fresh-inserts',
    'defectdojo-preflight', 'defectdojo-private-ingress',
})
STATUSES = frozenset({'PASS', 'FAIL', 'WARN', 'SKIP'})
COUNT_FIELDS = (
    'missingRunningSecrets', 'unverifiedRunningSecrets',
    'missingDeferredSecrets', 'unverifiedDeferredSecrets',
    'blockedCoreApps', 'coreDependencyBlockers',
    'blockedDeferredApps', 'deferredDependencyBlockers',
    'runningDeferredExcluded', 'plannedOrDisabledDeferred',
    'declaredCoreInactive', 'unmappedApps',
)


def read_bounded(file: Path, parent: Path, limit: int) -> str | None:
    if file.parent != parent or file.is_symlink() or not file.is_file():
        return None
    try:
        if file.stat().st_size > limit:
            return None
        return file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def classify_text(phase: str, value: str) -> str:
    """Emit only constant categories; avoid printing captured matches."""
    low = value.lower()
    # Logs contain benign banners and remediation hints. Prefer actual
    # failure lines over matches in instructional text or success messages.
    failures = '\n'.join(
        line.lower() for line in value.splitlines()
        if re.search(r'(?i)(?:❌|^\s*(?:error|fail|blocked):|migration conflict:)', line)
    )[:8192]
    if phase == 'postmigration-catalog':
        if 'stale catalog-v2 artifacts:' in low:
            return 'generated_catalog_drift'
        if 'modulenotfounderror' in low or 'no module named' in low:
            return 'generator_dependency_missing'
        return 'catalog_validation_failed'
    if phase in {'canonical-secret-files', 'first-wave-env', 'openrag-env-migration'}:
        # Do not interpret "no source conflicts" as an actual conflict.
        if re.search(r'migration conflict:|differs semantically|source conflict:', failures):
            return 'secret_source_conflict'
        if re.search(r'permission denied|owner/mode=|mode=[0-7]{3,4}|expected=root:root 600|acl denied', failures):
            return 'secret_permissions_or_owner'
        if re.search(r'empty-placeholder|empty secret|zero-byte', failures):
            return 'secret_empty_placeholder'
        if re.search(r'no recoverable source|missing.*secret|not found|requires staging|require staging|materialization.*missing|canonical env materialization', failures):
            return 'secret_materialization_missing_or_unstaged'
        if 'finalize pending' in failures:
            return 'legacy_finalize_pending'
        return 'secret_migration_failure_needs_private_detail'
    if phase.startswith('akvorado-'):
        if re.search(r'metadata missing|metadata_missing|rejected.*metadata|missing metadata', low):
            return 'netflow_metadata_rejected'
        if re.search(r'no (fresh )?insert|no batch|0 (batch|insert)|insert.*0', low):
            return 'clickhouse_inserts_unverified'
        return 'akvorado_runtime_unverified'
    if phase in {'postmigration-prometheus', 'prometheus-targets'}:
        if '401' in low or 'unauthorized' in low:
            return 'prometheus_scrape_auth_failure'
        if 'connection refused' in low or 'tcp_refused' in low:
            return 'prometheus_exporter_tcp_refused'
        return 'prometheus_scrapes_degraded_or_unverified'
    if phase == 'sentry-recovery-preflight':
        # "Sentry runtime credential preflight" is printed unconditionally
        # as a heading, including when only the app diagnostic fails.
        if re.search(r'deploying|crashed|unhealthy|restart', failures):
            return 'sentry_runtime_state_blocked'
        if re.search(r'credentials?|password|authentication|secret', failures):
            return 'sentry_credential_preflight_blocked'
        return 'sentry_preflight_blocked_unknown_cause'
    if phase == 'postmigration-gatus':
        # Seeing a field named "down" does not prove down > 0.
        if re.search(r'(?:["\x27]?down["\x27]?\s*[:=]\s*)(?:[1-9][0-9]*)\b', low):
            return 'gatus_monitors_observed_down'
        return 'gatus_monitor_data_unverified'
    if phase == 'postmigration-service-readiness':
        if re.search(r'healthcheck|unhealthy', low):
            return 'container_healthcheck_failure'
        return 'service_functional_readiness_failure'
    return 'runtime_gate_failed_unclassified'


def classify_wave(raw: str, wave: str) -> tuple[str, dict[str, int]]:
    try:
        data = json.loads(raw)
    except ValueError:
        return 'catalog_plan_invalid_json', {}
    if not isinstance(data, dict) or data.get('selectedWave') != wave or type(data.get('selectedWaveReady')) is not bool:
        return 'catalog_plan_invalid_schema', {}
    # The plan repeats global fields in every wave. Report only blockers
    # which validate_wave() actually enforces for the selected wave.
    scoped = {
        'core': (
            'missingRunningSecrets', 'unverifiedRunningSecrets',
            'blockedCoreApps', 'coreDependencyBlockers',
            'declaredCoreInactive', 'runningDeferredExcluded',
        ),
        'gatus': (
            'gatusBlocked', 'gatusMissingSecret', 'gatusSecretUnverified',
            'gatusDeclaredInactive',
        ),
        'deferred': (
            'missingDeferredSecrets', 'unverifiedDeferredSecrets',
            'blockedDeferredApps', 'plannedOrDisabledDeferred',
            'runningDeferredExcluded', 'deferredDependencyBlockers',
        ),
    }[wave]
    counts = {}
    for key in scoped:
        value = data.get(key)
        if isinstance(value, list):
            counts[key] = min(len(value), 10000)
        elif type(value) is bool:
            counts[key] = int(value)
    # These are inventory observations, not necessarily blockers.
    inventory = data.get('unmappedApps')
    if isinstance(inventory, list):
        counts['inventoryUnmappedTotal'] = min(len(inventory), 10000)
    if wave == 'gatus':
        state = data.get('states')
        if isinstance(state, dict) and state.get('gatus') not in ('RUNNING', 'STOPPED'):
            counts['gatusInvalidState'] = 1
    secrets = sum(counts.get(key, 0) for key in (
        'missingRunningSecrets', 'unverifiedRunningSecrets',
        'missingDeferredSecrets', 'unverifiedDeferredSecrets',
        'gatusMissingSecret', 'gatusSecretUnverified'))
    deps = sum(counts.get(key, 0) for key in (
        'blockedCoreApps', 'coreDependencyBlockers', 'blockedDeferredApps',
        'deferredDependencyBlockers', 'runningDeferredExcluded',
        'plannedOrDisabledDeferred', 'declaredCoreInactive',
        'gatusBlocked', 'gatusDeclaredInactive', 'gatusInvalidState'))
    if data['selectedWaveReady']:
        return 'wave_plan_ready_not_runtime_acceptance', counts
    if secrets and deps:
        return 'wave_blocked_secrets_and_dependencies', counts
    if secrets:
        return 'wave_blocked_runtime_secrets', counts
    if deps:
        return 'wave_blocked_dependency_or_lifecycle', counts
    return 'wave_blocked_other', counts


def analyze(folder: Path, root: Path = ROOT) -> dict:
    """Refuse symlinks and any input that escapes the private session root."""
    if (folder.parent != root or not SESSION.fullmatch(folder.name)
            or root.is_symlink() or folder.is_symlink() or not folder.is_dir()):
        raise ValueError('invalid_session_location')
    summary = read_bounded(folder / 'summary.tsv', folder, 16384)
    if summary is None:
        raise ValueError('private_summary_unavailable')
    rows = list(csv.reader(summary.splitlines(), delimiter='\t'))
    if not rows or rows[0] != ['phase', 'result', 'log'] or len(rows) > 65:
        raise ValueError('invalid_summary_format')
    result = []
    seen: set[str] = set()
    for row in rows[1:]:
        if len(row) != 3:
            raise ValueError('invalid_summary_row')
        name, status, raw_path = row
        if name not in PHASES or name in seen or status not in STATUSES:
            raise ValueError('unexpected_phase_or_status')
        seen.add(name)
        if status == 'SKIP':
            result.append({'phase': name, 'state': status, 'category': 'not_checked'})
            continue
        is_wave = name.startswith('catalog-')
        extension = '.json' if is_wave else '.log'
        candidate = Path(raw_path)
        raw = (read_bounded(candidate, folder, 262144)
               if candidate.is_absolute() and candidate.name == name + extension else None)
        if raw is None:
            item: dict = {'phase': name, 'state': status, 'category': 'private_evidence_unavailable'}
        elif is_wave:
            kind, counts = classify_wave(raw, name[len('catalog-'):])
            item = {'phase': name, 'state': status, 'category': kind, 'blocker_counts': counts}
        elif status == 'PASS':
            item = {'phase': name, 'state': status, 'category': 'passed'}
        else:
            item = {'phase': name, 'state': status, 'category': classify_text(name, raw)}
        result.append(item)
    if not result:
        raise ValueError('empty_session')
    return {
        'checks': result,
        'failed': sum(x['state'] == 'FAIL' for x in result),
        'unverified': sum(x['state'] in {'WARN', 'SKIP'} or x['category'] == 'private_evidence_unavailable'
                          for x in result),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--session', type=Path, action='append', required=True)
    args = parser.parse_args(argv)
    if len(args.session) > 6:
        parser.error('maximum six sessions')
    reports = []
    failed = False
    for item in args.session:
        try:
            result = analyze(item)
        except ValueError:
            result = {'checks': [], 'failed': 0, 'unverified': 1,
                      'status': 'session_unavailable'}
        failed |= result['failed'] > 0 or result['unverified'] > 0
        reports.append({'session_number': len(reports) + 1, **result})
    print(json.dumps({'sessions': reports}, sort_keys=True))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
