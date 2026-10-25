"""Offline regression tests; no LAN, Docker, or private TrueNAS files."""
import importlib.util
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts/truenas/triage-postmigration-report.py'
spec = importlib.util.spec_from_file_location('report_triage', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def session(tmp_path, rows):
    root = tmp_path / 'evidence'
    root.mkdir()
    folder = root / 'session-Ab123456'
    folder.mkdir()
    content = ['phase\tresult\tlog']
    for name, state, payload in rows:
        log = folder / (name + '.log')
        log.write_text(payload)
        content.append(f'{name}\t{state}\t{log}')
    (folder / 'summary.tsv').write_text('\n'.join(content) + '\n')
    return root, folder


def test_categories_no_secret_echo(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-catalog', 'FAIL', 'generated drift TOKEN=very-secret https://internal.local/private'),
        ('postmigration-service-readiness', 'FAIL', 'healthcheck unhealthy BEARER never-show'),
        ('postmigration-gatus', 'FAIL', json.dumps({'source':'gatus_lan_read_only','declared':85,'runtime':85,'up':61,'down':24,'unverified':0})),
        ('postmigration-prometheus', 'FAIL', 'Unhealthy targets HTTP 401 Authorization abc'),
    ])
    res = module.analyze(folder, root)
    assert res['failed'] == 4
    assert [x['category'] for x in res['checks']] == [
        'generated_catalog_drift', 'runtime_or_healthcheck_failed',
        'observed_monitors_down', 'prometheus_scrape_degraded',
    ]
    assert res['checks'][2]['evidence']['down'] == 24
    assert all(v not in json.dumps(res) for v in ['very-secret', 'never-show', 'abc', 'internal.local'])


def test_apisix_unknown_without_pretending_failure(tmp_path):
    root, folder = session(tmp_path,[('apisix-runtime','WARN','runtime=not_deployed_or_ambiguous http=not_checked')])
    res=module.analyze(folder, root)
    assert res['failed'] == 0 and res['unverified'] == 1
    assert res['checks'][0]['category'] == 'optional_gateway_unverified'


def test_bad_summary_rejected(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','hello')])
    summary=folder/'summary.tsv'
    summary.write_text('phase\tresult\tlog\nunknown-service\tPASS\t/etc/passwd\n')
    try:
        module.analyze(folder,root)
    except ValueError:
        pass
    else:
        assert False


def test_symlink_log_not_read(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','no such file SECRET=abc')])
    bad=folder/'postmigration-catalog.log'
    bad.unlink()
    bad.symlink_to('/etc/passwd')
    res=module.analyze(folder,root)
    assert res['checks'][0]['category'] == 'log_unavailable'


def test_symlink_session_rejected(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','PASS','ok')])
    link=root/'session-XY123456'
    link.symlink_to(folder,target_is_directory=True)
    try:
        module.analyze(link,root)
    except ValueError:
        pass
    else:
        assert False


def test_large_log_not_loaded(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','SECRET\n' * 30000)])
    res=module.analyze(folder,root)
    assert res['checks'][0]['category'] in {'log_unavailable','catalog_check_failed'}


def test_missing_pass_log_is_never_full_acceptance(tmp_path):
    root, folder = session(tmp_path,[('apisix-runtime','PASS','runtime=running')])
    (folder/'apisix-runtime.log').unlink()
    report=module.analyze(folder,root)
    assert report['checks'][0]['category']=='log_unavailable'
    assert report['complete'] is False
    assert report['unverified'] == 1

def test_partial_postmigration_summary_is_not_full_acceptance(tmp_path):
    root, folder = session(tmp_path,[('postmigration-catalog','PASS','catalog ok')])
    report=module.analyze(folder,root)
    assert report['complete'] is False
    assert 'postmigration-gatus' in report['missing_phases']
    assert report['unverified'] == 1


def test_prometheus_section_header_does_not_indicate_drift(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-prometheus', 'FAIL',
         '=== Prometheus config drift ===\n'
         'host and mounted Prometheus config match\n'
         'running-container Prometheus config is syntactically valid\n'
         'prometheus_runtime=running config_validation=passed target_up=21 target_not_up=7\n'
         'Unhealthy targets (job and health only; error category redacted):\n'
         'FAILED: 1 Prometheus validation problem(s) TOKEN_SECRET')
    ])
    result = module.analyze(folder, root)['checks'][0]
    assert result['category'] == 'prometheus_scrape_degraded'
    assert result['evidence']['target_up'] == 21
    assert result['evidence']['target_not_up'] == 7
    assert result['evidence']['signals'] == ['scrape_targets_degraded']
    assert 'TOKEN_SECRET' not in json.dumps(result)


def test_prometheus_real_config_mismatch_preserved(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-prometheus', 'FAIL',
         '=== Prometheus config drift ===\n'
         'host Prometheus config differs from the file visible inside the container\n'
         'prometheus_runtime=running config_validation=passed target_up=20 target_not_up=8\n')
    ])
    result = module.analyze(folder, root)['checks'][0]
    assert result['category'] == 'prometheus_config_or_rules'
    assert result['evidence']['signals'] == ['configuration_or_rules', 'scrape_targets_degraded']


def test_catalog_stale_generator_contract_is_classified(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-catalog', 'FAIL',
         'stale catalog-v2 artifacts:\n'
         ' - catalog/generated/identity-map.json\n'
         ' - catalog/generated/entities.json\n'
         'run: python scripts/generate-catalog-v2-artifacts.py\nSECRET')
    ])
    result = module.analyze(folder, root)['checks'][0]
    assert result['category'] == 'generated_catalog_drift'
    assert result['evidence']['stale_artifact_count'] == 2
    assert 'identity-map' not in json.dumps(result)
    assert 'SECRET' not in json.dumps(result)


def test_readiness_flags_only_allowlisted_service_ids(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-service-readiness', 'FAIL',
         'BLOCKED  scrutiny     TrueNAS=RUNNING\n'
         'DEGRADED openrag     TrueNAS=RUNNING\n'
         'BLOCKED  private-secret-url TrueNAS=RUNNING\n'
         'Summary: HEALTHY=6 BLOCKED=1 DEGRADED=1\n')
    ])
    result = module.analyze(folder, root)['checks'][0]
    assert result['evidence']['affected_count'] == 2
    assert result['evidence']['affected_services'] == [
        {'service': 'scrutiny', 'status': 'BLOCKED'},
        {'service': 'openrag', 'status': 'DEGRADED'},
    ]
    assert 'private-secret-url' not in json.dumps(result)


def test_readiness_note_no_healthcheck_does_not_mask_connectivity(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-service-readiness', 'FAIL',
         'BLOCKED  scrutiny     TrueNAS=RUNNING\n'
         '  · scrutiny no Docker healthcheck\n'
         '  · HTTP probe unavailable\n'
         'Summary: BLOCKED=1\n')
    ])
    result = module.analyze(folder, root)['checks'][0]
    assert result['category'] == 'functional_connection_failed'
    assert result['evidence']['affected_services'] == [
        {'service':'scrutiny', 'status':'BLOCKED'}
    ]
