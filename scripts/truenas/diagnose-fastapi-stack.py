#!/usr/bin/env python3
"""One bounded read-only diagnosis of FastAPI UI, Prometheus and AI/RAG.

No installs, secret values, Docker mutations, LLM requests, or CI runs.
Output includes only fixed codes, allowlisted component names and counts.
Run on TrueNAS for Docker evidence; browser checks are explicit opt-in.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
UI_TARGETS = {
    'truenas': 'http://172.17.0.24:8091',
    'staging': 'https://sample.albandrieu.com',
    'cloud': 'https://fastapi-sample.fastapicloud.dev',
}
UI_PATHS = ('/api', '/api/ui/session', '/api/ui/services')
PROM_URL = 'http://172.17.0.24:9090/api/v1/targets?state=active'
PROM_JOBS = (
    'fastapi_sample', 'litellm_hermes', 'postgres_exporter',
    'redis_exporter', 'pfsense_exporter', 'haproxy', 'opensearch',
    'opensearch-security', 'pihole_exporter', 'docling', 'gatus',
)
VERDICTS = ('PASS', 'FAIL', 'DENIED', 'UNVERIFIED', 'NOT_RUN')
SAFE_VALUE = re.compile(r'^[a-zA-Z0-9_./-]{1,90}$')
MAX_JSON_BYTES = 32768


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def safe(value: Any) -> str:
    """Never propagate an unknown child field or raw error message."""
    return value if isinstance(value, str) and SAFE_VALUE.fullmatch(value) else 'unverified'


def row(component: str, verdict: str, state: str, **numeric: object) -> dict[str, object]:
    assert verdict in VERDICTS
    return {'component': component, 'verdict': verdict, 'state': safe(state),
            **{key: val for key, val in numeric.items()
               if isinstance(val, int) and not isinstance(val, bool) and val >= 0}}


def run(argv: list[str], timeout: int = 20) -> tuple[str, dict[str, object], str]:
    """Execute pinned local scripts; capture no stderr and never forward raw output."""
    try:
        process = subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 check=False, timeout=timeout)
    except FileNotFoundError:
        return 'missing', {}, ''
    except subprocess.TimeoutExpired:
        return 'timeout', {}, ''
    except OSError:
        return 'unavailable', {}, ''
    output = process.stdout or b''
    if len(output) > MAX_JSON_BYTES:
        return 'invalid', {}, ''
    try:
        report = json.loads(output)
    except (ValueError, UnicodeError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    # String kept privately for the fixed-pattern Prometheus config diagnostic.
    return ('ok' if process.returncode == 0 else 'nonzero'), report, output.decode('utf-8', errors='replace')


def get_json(url: str, timeout: int = 5, limit: int = 1024 * 1024) -> dict[str, Any]:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={'Accept': 'application/json'}), timeout=timeout) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('too large')
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise ValueError('unexpected document')
    return doc


def ui_http() -> list[dict[str, object]]:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    output = []
    for name, origin in UI_TARGETS.items():
        codes = []
        for path in UI_PATHS:
            try:
                with opener.open(Request(origin + path, headers={'Accept': 'application/json'}),
                                 timeout=7 if path.endswith('/services') else 4) as response:
                    codes.append(response.status)
            except HTTPError as exc:
                codes.append(exc.code)
                exc.close()
            except (OSError, URLError, ValueError):
                codes.append(0)
        if all(code == 200 for code in codes):
            verdict, state = 'PASS', 'three_http_200'
        elif any(code in (401, 403) for code in codes):
            verdict, state = 'DENIED', 'authorization_or_access_policy'
        elif any(code >= 500 or code == 0 for code in codes):
            verdict, state = 'UNVERIFIED', 'http_or_transport_degraded'
        else:
            verdict, state = 'UNVERIFIED', 'unexpected_http_status'
        output.append(row('ui_' + name, verdict, state,
                          api_http=codes[0], session_http=codes[1], services_http=codes[2]))
    return output


def prometheus() -> tuple[list[dict[str, object]], dict[str, object]]:
    """Exactly one snapshot, including both prior baseline and remaining scopes."""
    try:
        data = get_json(PROM_URL, limit=1024 * 1024)
        path = ROOT / 'scripts/prometheus/diagnose-failed-scrapes.py'
        if not path.is_file():
            raise ValueError('classifier missing')
        spec = importlib.util.spec_from_file_location('nabla_scrape_classify', path)
        if spec is None or spec.loader is None:
            raise ValueError('classifier unavailable')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        statuses = module.assess_targets(data, jobs=PROM_JOBS)
        targets = data['data']['activeTargets']
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError, AttributeError, ImportError):
        return [row('prometheus_snapshot', 'UNVERIFIED', 'targets_unavailable')], {}
    output = []
    for name in PROM_JOBS:
        item = statuses[name]
        state = item['state']
        domains = item['failure_domains']
        if state == 'scrape_up':
            verdict = 'PASS'
        elif 'auth' in domains:
            verdict = 'DENIED'
        elif state in ('scrape_down', 'scrape_partial'):
            verdict = 'FAIL'
        else:
            verdict = 'UNVERIFIED'
        # One fixed diagnostic category; no raw lastError, URLs or target labels.
        cause = next((x for x in ('auth', 'tcp', 'dns', 'timeout', 'tls', 'network', 'http')
                      if x in domains), 'none' if verdict == 'PASS' else 'unverified')
        output.append(row('scrape_' + name, verdict, cause,
                          up=item['targets_up'], total=item['targets_total']))
    summary = {
        'snapshot_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'targets_total': len(targets),
        'targets_up': sum(t.get('health') == 'up' for t in targets if isinstance(t, dict)),
        'targets_not_up': sum(t.get('health') != 'up' for t in targets if isinstance(t, dict)),
    }
    return output, summary


def child_report(script: str, *args: str, timeout: int = 22) -> tuple[str, dict[str, object]]:
    path = ROOT / script
    if not path.is_file():
        return 'missing', {}
    status, data, _ = run([sys.executable, str(path), *args], timeout=timeout)
    return status, data


def readiness() -> list[dict[str, object]]:
    status, report = child_report('scripts/truenas/diagnose-service-readiness.py',
                                  '--check', '--service', 'openrag', '--service', 'litellm',
                                  '--service', 'prometheus', '--json', timeout=40)
    records = report.get('services')
    if not isinstance(records, list):
        return [row('app_readiness', 'NOT_RUN' if status == 'missing' else 'UNVERIFIED', 'probe_unavailable')]
    output = []
    for name in ('openrag', 'litellm', 'prometheus'):
        service = next((x for x in records if isinstance(x, dict) and x.get('service') == name), None)
        if service is None:
            output.append(row('app_' + name, 'UNVERIFIED', 'service_missing_from_report'))
            continue
        runtime, health = service.get('state'), service.get('status')
        if runtime == 'RUNNING' and health == 'HEALTHY':
            output.append(row('app_' + name, 'PASS', 'readiness_healthy'))
        elif runtime in ('STOPPED', 'CRASHED') or health == 'UNHEALTHY':
            output.append(row('app_' + name, 'FAIL', 'runtime_unhealthy'))
        else:
            output.append(row('app_' + name, 'UNVERIFIED', 'readiness_incomplete'))
    return output


def lite_keys() -> list[dict[str, object]]:
    status, report = child_report('scripts/truenas/check-fastapi-litellm-runtime-keys.py', '--check')
    entries = report.get('checks')
    if not isinstance(entries, dict):
        return [row('litellm_key_alignment', 'NOT_RUN' if status == 'missing' else 'UNVERIFIED', 'report_unavailable')]
    output = []
    for key, label in (('LITELLM_API_KEY', 'litellm_sample_key'),
                       ('LITELLM_FASTAPI_WORKSTATION_API_KEY', 'litellm_upstream_key')):
        entry = entries.get(key)
        if not isinstance(entry, dict):
            output.append(row(label, 'UNVERIFIED', 'key_check_missing'))
            continue
        container_state = entry.get('container_state')
        file_state = entry.get('file_state')
        equal = entry.get('file_vs_container')
        if container_state == 'container_key_absent':
            output.append(row(label, 'FAIL', 'container_key_absent'))
        elif equal == 'match':
            output.append(row(label, 'PASS', 'file_container_match_only'))
        elif container_state == 'container_key_present' and file_state == 'file_key_ambiguous':
            output.append(row(label, 'UNVERIFIED', 'file_key_ambiguous'))
        else:
            output.append(row(label, 'UNVERIFIED', 'alignment_not_verified'))
    return output


def upstream() -> list[dict[str, object]]:
    status, report = child_report('scripts/truenas/diagnose-workstation-litellm-upstream-auth.py', '--check')
    if report.get('host_context') != 'truenas_verified':
        return [row('litellm_upstream', 'NOT_RUN' if status == 'missing' else 'UNVERIFIED', 'truenas_identity_unverified')]
    key_state = report.get('truenas_upstream_key_state')
    living = report.get('workstation_liveliness')
    if key_state == 'missing_runtime_upstream_key':
        return [row('litellm_upstream', 'FAIL', 'missing_runtime_upstream_key')]
    if key_state == 'all_present_unvalidated' and living == 'http_200':
        return [row('litellm_upstream', 'UNVERIFIED', 'upstream_auth_not_tested')]
    return [row('litellm_upstream', 'UNVERIFIED', 'upstream_unverified')]


def ai_connectivity() -> list[dict[str, object]]:
    status, report = child_report('scripts/truenas/accept-fastapi-ai-connectivity.py', '--check', timeout=75)
    if report.get('component') != 'fastapi_ai_acceptance':
        return [row('ai_from_sample', 'NOT_RUN' if status == 'missing' else 'UNVERIFIED', 'container_probe_unavailable')]
    checks = (
        ('litellm', 'litellm'), ('litellm_model', 'fastapi_qwen_model'),
        ('openrag_backend', 'openrag_backend'), ('openrag_frontend', 'openrag_frontend'),
        ('openrag_mcp', 'openrag_mcp'), ('openrag_private_retrieval', 'openrag_private_retrieval'),
    )
    output = []
    for field, name in checks:
        value = report.get(field)
        if field in ('openrag_mcp', 'openrag_private_retrieval'):
            output.append(row(name, 'NOT_RUN' if value in ('not_tested', 'not_requested') else 'UNVERIFIED',
                              'mcp_handshake_not_verified' if field == 'openrag_mcp' else 'private_retrieval_not_verified'))
        elif value == 'http_200' or (field == 'litellm_model' and value == 'visible'):
            output.append(row(name, 'PASS', 'http_or_model_visible'))
        elif value in ('http_401', 'http_403'):
            output.append(row(name, 'DENIED', 'authenticated_request_denied'))
        elif value in ('tcp_refused', 'dns_failure', 'http_500', 'http_502', 'http_503'):
            output.append(row(name, 'FAIL', 'transport_or_server_failure'))
        else:
            output.append(row(name, 'UNVERIFIED', 'functional_probe_unverified'))
    return output


def ai_chain() -> list[dict[str, object]]:
    status, report = child_report('scripts/truenas/diagnose-fastapi-ai-chain.py', '--check', '--runtime', timeout=45)
    if report.get('component') != 'fastapi_truenas_ai_rag':
        return [row('ai_chain', 'NOT_RUN' if status == 'missing' else 'UNVERIFIED', 'probe_unavailable')]
    runtime = report.get('runtime')
    declared = report.get('declared')
    if not isinstance(runtime, dict) or not isinstance(declared, dict):
        return [row('ai_chain', 'UNVERIFIED', 'report_unavailable')]
    output = []
    for field in ('litellm', 'ollama', 'openrag_backend'):
        value = runtime.get(field)
        output.append(row('ai_transport_' + field,
                          'PASS' if value == 'http_200' else 'DENIED' if value in ('http_401', 'http_403') else 'UNVERIFIED',
                          'http_200' if value == 'http_200' else 'transport_unverified'))
    mcp = runtime.get('openrag_mcp')
    output.append(row('ai_transport_openrag_mcp', 'UNVERIFIED',
                      'mcp_protocol_not_authenticated' if mcp in ('http_200', 'http_401', 'http_405', 'http_406')
                      else 'mcp_transport_unverified'))
    output.append(row('ai_openrag_integration', 'UNVERIFIED',
                      'private_acl_pending' if declared.get('fastapi_openrag_mcp') == 'not_wired_pending_private_acl'
                      else 'integration_not_accepted'))
    return output


def metrics_auth(fastapi_root: Path | None) -> list[dict[str, object]]:
    script = (fastapi_root / 'scripts/truenas/diagnose-fastapi-metrics-auth.py'
              if fastapi_root is not None else None)
    if script is None or not script.is_file():
        return [row('fastapi_metrics_auth', 'NOT_RUN', 'fastapi_checkout_unavailable')]
    status, report, _ = run([sys.executable, str(script), '--check'], timeout=18)
    value = report.get('state')
    if value == 'scrape_auth_accepted':
        return [row('fastapi_metrics_auth', 'PASS', 'scrape_auth_accepted')]
    if value == 'unexpected_anonymous_metrics_access':
        return [row('fastapi_metrics_auth', 'FAIL', 'unexpected_anonymous_access')]
    if value == 'scrape_credential_rejected':
        return [row('fastapi_metrics_auth', 'DENIED', 'scrape_credential_rejected')]
    return [row('fastapi_metrics_auth', 'UNVERIFIED', 'metrics_token_evidence_incomplete')]


def browser(fastapi_root: Path | None) -> list[dict[str, object]]:
    script = (fastapi_root / 'scripts/diagnose-production-api-ui-freeze.mjs'
              if fastapi_root is not None else None)
    if script is None or not script.is_file():
        return [row('ui_chromium', 'NOT_RUN', 'fastapi_checkout_unavailable')]
    status, report, _ = run(['node', str(script), 'truenas', '--preflight'], timeout=10)
    if report.get('state') != 'browser_binary_ready':
        return [row('ui_chromium', 'NOT_RUN', 'browser_not_installed')]
    output = []
    for target in ('truenas', 'cloud'):
        for mode, flags in (('safe', ['--safe']), ('full', ['--full'])):
            status, result, _ = run(['node', str(script), target, *flags, '--native'], timeout=48)
            value = result.get('state')
            if value == 'sampled':
                verdict, reason = 'PASS', 'dom_sampled_not_manual_acceptance'
            elif value in ('http_access_restricted', 'redirected_off_origin'):
                verdict, reason = 'DENIED', 'access_restricted'
            elif value in ('main_thread_unresponsive', 'ui_loading_without_content'):
                verdict, reason = 'FAIL', 'browser_ui_not_responsive'
            else:
                verdict, reason = 'UNVERIFIED', 'browser_sample_unverified'
            output.append(row('ui_chromium_' + target + '_' + mode, verdict, reason))
    return output


def deep_prometheus() -> list[dict[str, object]]:
    script = ROOT / 'scripts/truenas/diagnose-prometheus-targets.sh'
    if not script.is_file():
        return [row('prometheus_config', 'NOT_RUN', 'script_missing')]
    status, _report, raw = run(['bash', str(script), '--check'], timeout=65)
    if status in ('missing', 'timeout', 'unavailable', 'invalid'):
        return [row('prometheus_config', 'UNVERIFIED', 'config_probe_unavailable')]
    matched = 'host and mounted Prometheus config match' in raw
    valid = 'running-container Prometheus config is syntactically valid' in raw
    # Do not infer config failure solely from a shell exit 1: exporter DOWN
    # is reported by the same command after promtool succeeds.
    return [row('prometheus_config', 'PASS' if matched and valid else 'UNVERIFIED',
                'config_valid_and_in_sync' if matched and valid else 'config_unverified')]


def is_truenas() -> bool:
    """TrueNAS middleware check; no output, never trust local Docker elsewhere."""
    if shutil.which('midclt') is None:
        return False
    try:
        completed = subprocess.run(['midclt', 'call', 'system.info'],
                                   stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   check=False, timeout=6)
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def openrag_dependencies() -> list[dict[str, object]]:
    script = ROOT / 'scripts/truenas/diagnose-openrag-dependencies.sh'
    if not script.is_file():
        return [row('openrag_dependencies', 'NOT_RUN', 'script_missing')]
    status, _, raw = run(['bash', str(script), '--check'], timeout=30)
    if status == 'ok' and 'OK: OpenRAG backend/frontend running+healthy' in raw:
        return [row('openrag_dependencies', 'PASS', 'backend_frontend_dependencies_ready')]
    if status == 'nonzero' and 'BLOCKED:' in raw:
        return [row('openrag_dependencies', 'FAIL', 'dependency_blocked')]
    return [row('openrag_dependencies', 'UNVERIFIED', 'dependency_check_unverified')]


def default_fastapi_root() -> Path | None:
    for candidate in (
        ROOT / 'fastapi-sample',
        ROOT.parent / 'fastapi-sample',
        Path('/mnt/cpool/compose/nabla-compose/fastapi-sample'),
    ):
        if (candidate / 'scripts/truenas/diagnose-fastapi-metrics-auth.py').is_file():
            return candidate
    return None


def brief_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep actionable findings and collapse only proven duplicate causes.

    All original checks remain in JSON and summary counters. In particular,
    a missing upstream key explains both its alignment and relay failure;
    HTTP transport 200 alone does not override the authenticated 401.
    """
    upstream_missing = any(
        r.get('component') == 'litellm_upstream_key'
        and r.get('state') == 'container_key_absent' for r in rows
    )
    shown_mcp = False
    findings: list[dict[str, object]] = []
    for record in rows:
        if record.get('verdict') == 'PASS':
            continue
        component = record.get('component')
        if upstream_missing and component == 'litellm_upstream' and (
            record.get('state') == 'missing_runtime_upstream_key'
        ):
            continue
        if component == 'ai_transport_openrag_mcp' and shown_mcp:
            continue
        if component == 'openrag_mcp':
            shown_mcp = True
        findings.append(record)
    return findings


def summarize(rows: list[dict[str, object]]) -> dict[str, int]:
    return {v: sum(r['verdict'] == v for r in rows) for v in VERDICTS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--scope', choices=('all', 'ui', 'prometheus', 'ai'), default='all')
    parser.add_argument('--json', action='store_true', help='Print redacted JSON rather than concise text')
    parser.add_argument('--brief', action='store_true', help='Show unresolved checks only; deduplicate known causes')
    parser.add_argument('--browser', action='store_true', help='Opt-in Chromium with preinstalled Playwright only')
    parser.add_argument('--deep-prometheus', action='store_true', help='Opt-in promtool and config-bind audit')
    parser.add_argument('--fastapi-root', type=Path, help='Local FastAPI checkout for metrics and optional Chromium')
    args = parser.parse_args(argv)
    fastapi_root = args.fastapi_root.resolve() if args.fastapi_root else default_fastapi_root()
    rows: list[dict[str, object]] = []
    evidence: dict[str, object] = {}
    if args.scope in ('all', 'ui'):
        rows.extend(ui_http())
        if args.browser:
            rows.extend(browser(fastapi_root))
    verified_truenas = is_truenas()
    if args.scope in ('all', 'prometheus'):
        prom, snapshot = prometheus()
        rows.extend(prom)
        if snapshot:
            evidence['prometheus'] = snapshot
        rows.extend(metrics_auth(fastapi_root) if verified_truenas else
                    [row('fastapi_metrics_auth', 'NOT_RUN', 'truenas_host_required')])
        if args.deep_prometheus:
            rows.extend(deep_prometheus())
    if args.scope in ('all', 'ai'):
        if not verified_truenas:
            rows.append(row('ai_truenas_runtime', 'NOT_RUN', 'truenas_host_required'))
        else:
            rows.extend(readiness())
            rows.extend(openrag_dependencies())
            rows.extend(lite_keys())
            rows.extend(upstream())
            rows.extend(ai_connectivity())
            rows.extend(ai_chain())
    summary = summarize(rows)
    decision = ('BLOCKED' if summary['FAIL'] else
                'INCOMPLETE' if any(summary[k] for k in ('UNVERIFIED', 'DENIED', 'NOT_RUN'))
                else 'PRECHECK_PASS_MANUAL_ACCEPTANCE_REQUIRED')
    report = {'schema': 'nabla-fastapi-stack-diagnostic/v1', 'read_only': True,
              'scope': args.scope, 'checks': rows, 'summary': summary,
              'evidence': evidence, 'decision': decision,
              'cloud_ui_manual_acceptance': 'NOT_RUN',
              'openrag_private_retrieval_acceptance': 'NOT_RUN'}
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print('FastAPI consolidated diagnostics | ' + decision)
        selected = brief_rows(rows) if args.brief else rows
        for item in selected:
            details = ' '.join(f'{key}={value}' for key, value in item.items()
                               if key not in ('component', 'verdict', 'state'))
            print(f"{item['verdict']:10} {item['component']:33} {item['state']} {details}".rstrip())
        if evidence.get('prometheus'):
            snap = evidence['prometheus']
            print(f"Prometheus single snapshot: {snap['targets_up']}/{snap['targets_total']} up; "
                  f"not_up={snap['targets_not_up']}; at={snap['snapshot_utc']}")
        print('Summary ' + ' '.join(f'{v}={summary[v]}' for v in VERDICTS))
        if args.brief:
            print(f'Brief unresolved findings={len(selected)} (full check count preserved in JSON)')
        print('Cloud UI manual acceptance: NOT_RUN; OpenRAG private retrieval: NOT_RUN')
    return 1 if summary['FAIL'] else 2 if decision == 'INCOMPLETE' else 0


if __name__ == '__main__':
    raise SystemExit(main())
